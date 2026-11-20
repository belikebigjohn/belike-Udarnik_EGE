"""Udarny Efir: dependency-free HTTP API, SQLite progress, and Telegram polling bot."""
import learning
import exam
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "data/words.json").read_text(encoding="utf-8"))
WORDS = {w["id"]: w for w in DATA["entries"]}
EXAM_BANK = exam.load_bank()
QUESTIONS = learning.catalog(WORDS)
QUESTIONS.update(exam.review_adapters(EXAM_BANK))
DB = Path(os.getenv("DATABASE_PATH", ROOT / "data/progress.sqlite3"))
TOKEN = os.getenv("BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "")
DEV = os.getenv("DEV_MODE", "0") == "1"
PORT = int(os.getenv("PORT", "8080"))
REMINDER_HOUR_UTC = int(os.getenv("REMINDER_HOUR_UTC", "12"))
VOWELS = "аеёиоуыэюя"
DB_INIT_LOCK = threading.RLock()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def db():
    with DB_INIT_LOCK:
        conn = sqlite3.connect(DB, timeout=20, factory=ClosingConnection)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, reminders INTEGER NOT NULL DEFAULT 0, last_reminder_day TEXT);
            CREATE TABLE IF NOT EXISTS progress (user_id INTEGER, word_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                mistakes INTEGER NOT NULL DEFAULT 0, streak_days INTEGER NOT NULL DEFAULT 0, last_correct_day TEXT,
                due_at TEXT NOT NULL, PRIMARY KEY(user_id,word_id));
            CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, word_id TEXT,
                chosen_index INTEGER, correct INTEGER, answered_at TEXT, mode TEXT);
            CREATE TABLE IF NOT EXISTS rounds (id TEXT PRIMARY KEY, user_id INTEGER, queue TEXT, position INTEGER DEFAULT 0,
                outcomes TEXT, finished INTEGER DEFAULT 0, created_at TEXT);
            CREATE TABLE IF NOT EXISTS quizzes (id TEXT PRIMARY KEY, user_id INTEGER, options TEXT, correct TEXT,
                answered INTEGER DEFAULT 0, created_at TEXT);
            """)
            learning.migrate(conn)
            exam.migrate(conn)
            return conn
        except Exception:
            conn.close()
            raise


def utcnow():
    return datetime.now(timezone.utc)


def authenticate(init_data):
    # DEV_MODE binds HTTP to loopback below; allow a local browser preview even
    # when BOT_TOKEN is present in the developer's environment.
    if DEV and init_data == "dev":
        return 1
    if not TOKEN or not init_data:
        raise ValueError("Откройте приложение через Telegram")
    values = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
    fields = dict(values)
    received = fields.pop("hash", "")
    if len(values) != len(fields) + 1 or not received:
        raise ValueError("Некорректные данные Telegram")
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise ValueError("Подпись Telegram не совпала")
    age = time.time() - int(fields.get("auth_date", "0"))
    if age < -60 or age > 86400:
        raise ValueError("Данные Telegram устарели — откройте приложение снова")
    user_id = json.loads(fields["user"])["id"]
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("Нет Telegram ID")
    return user_id


def ensure_user(conn, uid):
    conn.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))


def stats(conn, uid):
    now = utcnow().isoformat()
    row = conn.execute("""SELECT
      SUM(CASE WHEN streak_days>=3 THEN 1 ELSE 0 END) learned,
      SUM(CASE WHEN due_at<=? THEN 1 ELSE 0 END) due,
      SUM(CASE WHEN mistakes>0 AND streak_days<3 THEN 1 ELSE 0 END) confused
      FROM progress WHERE user_id=?""", (now, uid)).fetchone()
    return {k: row[k] or 0 for k in ("learned", "due", "confused")}


def public_word(word):
    return {k: word[k] for k in ("id", "form", "category", "note", "footnote")}


def current_round(conn, uid):
    row = conn.execute("SELECT * FROM rounds WHERE user_id=? AND finished=0 ORDER BY created_at DESC LIMIT 1", (uid,)).fetchone()
    if not row:
        return None
    queue = json.loads(row["queue"])
    if row["position"] >= len(queue):
        return None
    return {"id": row["id"], "position": row["position"] + 1, "total": len(queue),
            "word": public_word(WORDS[queue[row["position"]]])}


def start_round(conn, uid):
    active = current_round(conn, uid)
    if active:
        return active
    due = [r["word_id"] for r in conn.execute("SELECT word_id FROM progress WHERE user_id=? AND due_at<=? ORDER BY due_at", (uid, utcnow().isoformat())) if r["word_id"] in WORDS]
    seen = {r["word_id"] for r in conn.execute("SELECT word_id FROM progress WHERE user_id=?", (uid,))}
    fresh = [w["id"] for w in DATA["entries"] if w["id"] not in seen]
    random.shuffle(fresh)
    selected = due[:5] + fresh[:max(0, 10 - min(len(due), 5))]
    if len(selected) < 10:
        others = [w for w in WORDS if w not in selected]
        random.shuffle(others)
        selected += others[:10 - len(selected)]
    random.shuffle(selected)
    rid = secrets.token_urlsafe(14)
    conn.execute("INSERT INTO rounds(id,user_id,queue,outcomes,created_at) VALUES(?,?,?,?,?)",
                 (rid, uid, json.dumps(selected), "[]", utcnow().isoformat()))
    return current_round(conn, uid)


def record_answer(conn, uid, wid, chosen, correct, mode):
    learning.sync_legacy(conn, uid)
    now = utcnow()
    today = now.date().isoformat()
    old = conn.execute("SELECT * FROM progress WHERE user_id=? AND word_id=?", (uid, wid)).fetchone()
    attempts = (old["attempts"] if old else 0) + 1
    mistakes = (old["mistakes"] if old else 0) + (not correct)
    streak = old["streak_days"] if old else 0
    last = old["last_correct_day"] if old else None
    if not correct:
        streak = 0
        due = now + timedelta(days=1)
    elif last != today:
        streak += 1
        last = today
        due = now + timedelta(days=1 if streak == 1 else 3 if streak == 2 else 7 if streak == 3 else 14)
    else:
        due = datetime.fromisoformat(old["due_at"]) if old else now + timedelta(days=1)
    conn.execute("""INSERT INTO progress(user_id,word_id,attempts,mistakes,streak_days,last_correct_day,due_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,word_id) DO UPDATE SET attempts=excluded.attempts,
        mistakes=excluded.mistakes,streak_days=excluded.streak_days,last_correct_day=excluded.last_correct_day,due_at=excluded.due_at""",
        (uid, wid, attempts, mistakes, streak, last, due.isoformat()))
    conn.execute("INSERT INTO answers(user_id,word_id,chosen_index,correct,answered_at,mode) VALUES(?,?,?,?,?,?)",
                 (uid, wid, chosen, int(correct), now.isoformat(), mode))
    learning.record(conn, uid, "stress:" + wid, "stress", correct, mode)
    learning.unlock(conn, uid)
    return streak


def answer_round(conn, uid, payload):
    rid = payload.get("round_id")
    row = conn.execute("SELECT * FROM rounds WHERE id=? AND user_id=? AND finished=0", (rid, uid)).fetchone()
    if not row:
        raise ValueError("Раунд не найден")
    queue = json.loads(row["queue"])
    pos = row["position"]
    if pos >= len(queue) or payload.get("word_id") != queue[pos]:
        raise ValueError("Карточка уже отвечена")
    word = WORDS[queue[pos]]
    chosen = payload.get("index")
    if type(chosen) is not int or chosen < 0 or chosen >= len(word["form"]) or word["form"][chosen] not in VOWELS:
        raise ValueError("Выберите гласную")
    xp_before = conn.execute("SELECT COALESCE(SUM(xp),0) FROM learning_rewards WHERE user_id=?", (uid,)).fetchone()[0]
    correct = chosen == word["stress_index"]
    streak = record_answer(conn, uid, word["id"], chosen, correct, "round")
    outcomes = json.loads(row["outcomes"])
    gained = conn.execute("SELECT COALESCE(SUM(xp),0) FROM learning_rewards WHERE user_id=?", (uid,)).fetchone()[0] - xp_before
    outcomes.append({"xp": gained, "id": word["id"], "marked": word["marked"], "correct": correct, "mastered": streak >= 3})
    if not correct and len(queue) < 15:
        queue.insert(min(pos + 4, len(queue)), word["id"])
    finished = pos + 1 >= len(queue)
    conn.execute("UPDATE rounds SET queue=?,position=?,outcomes=?,finished=? WHERE id=?",
                 (json.dumps(queue), pos + 1, json.dumps(outcomes, ensure_ascii=False), int(finished), rid))
    result = {"correct": correct, "marked": word["marked"], "note": word["note"],
              "footnote": DATA["source"]["footnotes"].get(word["footnote"]), "audio_url": word["audio_url"],
              "mastered": streak >= 3, "finished": finished, "xp": gained}
    if finished:
        earned = learning.unlock(conn, uid, perfect=all(o["correct"] for o in outcomes))
        bonus = sum(a["xp"] for a in earned)
        outcomes[-1]["xp"] += bonus
        result["xp"] += bonus
        conn.execute("UPDATE rounds SET outcomes=? WHERE id=?", (json.dumps(outcomes, ensure_ascii=False), rid))
        result["summary"] = outcomes
    else:
        result["next"] = current_round(conn, uid)
    return result


DEMO = [
    {"shown": "озлОбить", "correct": True, "word_id": next(w["id"] for w in WORDS.values() if w["form"] == "озлобить")},
    {"shown": "нАчал", "correct": True, "word_id": next(w["id"] for w in WORDS.values() if w["form"] == "начал")},
    {"shown": "накрЕнятся", "correct": False, "word_id": None},
    {"shown": "аэропОрты", "correct": True, "word_id": next(w["id"] for w in WORDS.values() if w["form"] == "аэропорты")},
    {"shown": "заселЁнный", "correct": True, "word_id": next(w["id"] for w in WORDS.values() if w["form"] == "заселённый")},
]


def new_quiz(conn, uid):
    # First show the exact 2027 demonstration; subsequent sheets use only imported forms.
    prior = conn.execute("SELECT COUNT(*) FROM quizzes WHERE user_id=?", (uid,)).fetchone()[0]
    if prior == 0:
        options = [{"shown": o["shown"], "word_id": o["word_id"]} for o in DEMO]
        correct = [i + 1 for i, o in enumerate(DEMO) if o["correct"]]
        kind = "Демоверсия ФИПИ‑2027"
    else:
        pool = [w for w in WORDS.values() if len([c for c in w["form"] if c in VOWELS]) > 1]
        selected = random.sample(pool, 5)
        correct = sorted(random.sample(range(1, 6), random.choice((2, 3, 4))))
        options = []
        for i, w in enumerate(selected, 1):
            if i in correct:
                shown = w["marked"]
            else:
                wrong = random.choice([j for j, c in enumerate(w["form"]) if c in VOWELS and j != w["stress_index"]])
                shown = "".join(c.upper() if j == wrong else c.lower() for j, c in enumerate(w["form"]))
            options.append({"shown": shown, "word_id": w["id"]})
        kind = "Тренировка по формату задания 4"
    qid = secrets.token_urlsafe(14)
    conn.execute("INSERT INTO quizzes(id,user_id,options,correct,created_at) VALUES(?,?,?,?,?)",
                 (qid, uid, json.dumps(options, ensure_ascii=False), json.dumps(correct), utcnow().isoformat()))
    return {"id": qid, "kind": kind, "options": [o["shown"] for o in options]}


def answer_quiz(conn, uid, payload):
    row = conn.execute("SELECT * FROM quizzes WHERE id=? AND user_id=? AND answered=0", (payload.get("quiz_id"), uid)).fetchone()
    if not row:
        raise ValueError("Задание уже отвечено")
    chosen = payload.get("selected")
    if not isinstance(chosen, list) or any(type(n) is not int or n < 1 or n > 5 for n in chosen) or len(chosen) != len(set(chosen)):
        raise ValueError("Выберите номера вариантов")
    correct = json.loads(row["correct"])
    options = json.loads(row["options"])
    conn.execute("UPDATE quizzes SET answered=1 WHERE id=?", (row["id"],))
    xp_before = conn.execute("SELECT COALESCE(SUM(xp),0) FROM learning_rewards WHERE user_id=?", (uid,)).fetchone()[0]
    review = []
    for i, option in enumerate(options, 1):
        w = WORDS.get(option["word_id"])
        if w:
            record_answer(conn, uid, w["id"], w["stress_index"] if i in correct else -1,
                          (i in chosen) == (i in correct), "ege")
        review.append({"number": i, "shown": option["shown"], "correct": i in correct,
                       "marked": w["marked"] if w else "накренИтся (в списке: форма 3-го лица)",
                       "note": w["note"] if w else "В демоверсии дана другая личная форма; вариант с Е неверен."})
    learning.unlock(conn, uid, perfect=sorted(chosen) == correct)
    xp = conn.execute("SELECT COALESCE(SUM(xp),0) FROM learning_rewards WHERE user_id=?", (uid,)).fetchone()[0] - xp_before
    return {"passed": sorted(chosen) == correct, "correct_numbers": correct, "review": review, "xp": xp}


def telegram(method, data):
    request = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}",
        data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def bot_loop():
    if not TOKEN or not APP_URL:
        return
    telegram("setMyCommands", {"commands": [{"command": "start", "description": "Открыть тренировку"},
                                              {"command": "remind_on", "description": "Включить напоминания"},
                                              {"command": "remind_off", "description": "Выключить напоминания"}]})
    telegram("setChatMenuButton", {"menu_button": {"type": "web_app", "text": "Ударный эфир", "web_app": {"url": APP_URL}}})
    offset = 0
    while True:
        try:
            updates = telegram("getUpdates", {"offset": offset, "timeout": 25}).get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                uid = msg.get("from", {}).get("id")
                if not uid or msg.get("chat", {}).get("type") != "private":
                    continue
                command = msg.get("text", "").split()[0].split("@")[0]
                with db() as conn:
                    ensure_user(conn, uid)
                    if command == "/remind_on":
                        conn.execute("UPDATE users SET reminders=1 WHERE id=?", (uid,))
                        message = "Напоминания включены. Отключить: /remind_off"
                    elif command == "/remind_off":
                        conn.execute("UPDATE users SET reminders=0 WHERE id=?", (uid,))
                        message = "Напоминания выключены."
                    elif command == "/start":
                        message = "Вы — редактор эфира. Нажмите на ударную гласную, чтобы выпустить слово. 10–15 карточек в день, ошибки вернутся на повторение."
                    else:
                        continue
                telegram("sendMessage", {"chat_id": uid, "text": message,
                    "reply_markup": {"inline_keyboard": [[{"text": "Открыть тренировку", "web_app": {"url": APP_URL}}]]}})
        except Exception as exc:
            print("bot polling:", exc, flush=True)
            time.sleep(5)


def reminder_loop():
    if not TOKEN:
        return
    while True:
        try:
            now = utcnow()
            if now.hour == REMINDER_HOUR_UTC:
                day = now.date().isoformat()
                with db() as conn:
                    users = conn.execute("SELECT id FROM users WHERE reminders=1 AND COALESCE(last_reminder_day,'')<>?", (day,)).fetchall()
                    for user in users:
                        try:
                            telegram("sendMessage", {"chat_id": user["id"], "text": "Эфир ждёт: 5 минут на ударения сегодня.",
                                "reply_markup": {"inline_keyboard": [[{"text": "Открыть тренировку", "web_app": {"url": APP_URL}}]]}})
                            conn.execute("UPDATE users SET last_reminder_day=? WHERE id=?", (day, user["id"]))
                        except Exception as exc:
                            print("reminder:", exc, flush=True)
        except Exception as exc:
            print("reminder loop:", exc, flush=True)
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_api(self):
        try:
            uid = authenticate(self.headers.get("X-Telegram-Init-Data", ""))
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 10000:
                raise ValueError("Слишком большой запрос")
            payload = json.loads(self.rfile.read(length) or b"{}") if self.command == "POST" else {}
            if not isinstance(payload, dict):
                raise ValueError("Нужен JSON-объект")
            path = urllib.parse.urlparse(self.path).path
            with db() as conn:
                ensure_user(conn, uid)
                learning.sync_legacy(conn, uid)
                if path == "/api/home" and self.command == "GET":
                    body = {"stats": stats(conn, uid), "source": DATA["source"],
                            "word_count": len(WORDS),
                            "reminders": bool(conn.execute("SELECT reminders FROM users WHERE id=?", (uid,)).fetchone()[0]),
                            "round": current_round(conn, uid),
                            "learning": learning.dashboard(conn, uid, QUESTIONS)}
                elif path == "/api/exam/home" and self.command == "GET":
                    body = exam.dashboard(conn, uid, EXAM_BANK)
                elif path == "/api/exam/start" and self.command == "POST":
                    body = exam.start(conn, uid, payload, EXAM_BANK)
                elif path == "/api/exam/session" and self.command == "POST":
                    body = exam.session_view(conn, uid, payload.get("session_id"))
                elif path == "/api/exam/action" and self.command == "POST":
                    body = exam.mutate(conn, uid, payload)
                elif path == "/api/learning/start" and self.command == "POST":
                    body = learning.start(conn, uid, payload, QUESTIONS)
                elif path == "/api/learning/answer" and self.command == "POST":
                    body = learning.answer(conn, uid, payload, QUESTIONS)
                elif path == "/api/learning/session" and self.command == "POST":
                    body = learning.session_view(conn, uid, payload.get("session_id"), QUESTIONS)
                elif path == "/api/round" and self.command == "POST":
                    body = start_round(conn, uid)
                elif path == "/api/answer" and self.command == "POST":
                    body = answer_round(conn, uid, payload)
                elif path == "/api/quiz" and self.command == "POST":
                    body = new_quiz(conn, uid)
                elif path == "/api/quiz/answer" and self.command == "POST":
                    body = answer_quiz(conn, uid, payload)
                elif path == "/api/reminders" and self.command == "POST":
                    if type(payload.get("enabled")) is not bool:
                        raise ValueError("Укажите enabled")
                    conn.execute("UPDATE users SET reminders=? WHERE id=?", (int(payload["enabled"]), uid))
                    body = {"enabled": payload["enabled"]}
                else:
                    return self.respond(404, {"error": "Не найдено"})
            return self.respond(200, body)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": str(exc)})

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.handle_api()
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/", "/style.css", "/word.css", "/app.js", "/studio.js", "/studio.css", "/exam.js", "/exam.css"):
            return self.send_error(404)
        file = ROOT / "web" / ("index.html" if path == "/" else path[1:])
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}[file.suffix])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        return self.handle_api()


if __name__ == "__main__":
    DB.parent.mkdir(parents=True, exist_ok=True)
    with db():
        pass
    if TOKEN and APP_URL and not DEV:
        threading.Thread(target=bot_loop, daemon=True).start()
        threading.Thread(target=reminder_loop, daemon=True).start()
    host = "127.0.0.1" if DEV else "0.0.0.0"
    print(f"Ударный эфир: http://{host}:{PORT} ({len(WORDS)} entries)", flush=True)
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()
