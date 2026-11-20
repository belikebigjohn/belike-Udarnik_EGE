import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

import app
import import_fipi


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB = Path(self.temp.name) / "test.sqlite3"
        self.conn = app.db()
        app.ensure_user(self.conn, 101)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_import_is_reproducible_and_stress_is_valid(self):
        rows = import_fipi.parse()
        self.assertEqual(len(rows), 220)
        self.assertEqual([w["marked"] for w in rows if w["form"] == "отзыв"], ["Отзыв", "отзЫв"])
        self.assertIn("заняла", [w["form"] for w in rows])
        self.assertTrue(all(w["marked"][w["stress_index"]].isupper() for w in rows))
        self.assertEqual(len(rows), len(json.loads((Path(__file__).parent.parent / "data/words.json").read_text(encoding="utf-8"))["entries"]))

    def test_round_retry_and_cross_day_mastery(self):
        round_ = app.start_round(self.conn, 101)
        word = app.WORDS[round_["word"]["id"]]
        wrong = next(i for i, c in enumerate(word["form"]) if c in app.VOWELS and i != word["stress_index"]) if sum(c in app.VOWELS for c in word["form"]) > 1 else None
        if wrong is not None:
            result = app.answer_round(self.conn, 101, {"round_id": round_["id"], "word_id": word["id"], "index": wrong})
            self.assertFalse(result["correct"])
            queue = json.loads(self.conn.execute("SELECT queue FROM rounds WHERE id=?", (round_["id"],)).fetchone()[0])
            self.assertEqual(queue[4], word["id"])
        else:
            app.answer_round(self.conn, 101, {"round_id": round_["id"], "word_id": word["id"], "index": word["stress_index"]})
        app.record_answer(self.conn, 101, word["id"], word["stress_index"], True, "round")
        self.assertEqual(self.conn.execute("SELECT streak_days FROM progress WHERE user_id=101 AND word_id=?", (word["id"],)).fetchone()[0], 1)
        for expected in (2, 3):
            self.conn.execute("UPDATE progress SET last_correct_day=? WHERE user_id=101 AND word_id=?", (f"2026-11-{18-expected:02d}", word["id"]))
            self.assertEqual(app.record_answer(self.conn, 101, word["id"], word["stress_index"], True, "round"), expected)
        self.assertGreaterEqual(app.stats(self.conn, 101)["learned"], 1)
        self.conn.commit()
        with app.db() as other_device:
            self.assertGreaterEqual(app.stats(other_device, 101)["learned"], 1)
            self.assertEqual(app.stats(other_device, 202)["learned"], 0)

    def test_ege_demo_and_review(self):
        quiz = app.new_quiz(self.conn, 101)
        self.assertEqual(quiz["options"], ["озлОбить", "нАчал", "накрЕнятся", "аэропОрты", "заселЁнный"])
        result = app.answer_quiz(self.conn, 101, {"quiz_id": quiz["id"], "selected": [1, 2, 4, 5]})
        self.assertTrue(result["passed"])
        self.assertEqual(result["correct_numbers"], [1, 2, 4, 5])
        self.assertEqual(len(result["review"]), 5)
        with self.assertRaises(ValueError):
            app.answer_quiz(self.conn, 101, {"quiz_id": quiz["id"], "selected": [1, 2, 4, 5]})
        generated = app.new_quiz(self.conn, 101)
        self.assertEqual(len(generated["options"]), 5)

    def test_telegram_signature_and_expiry(self):
        old_token = app.TOKEN
        app.TOKEN = "123:secret"
        try:
            fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 77})}
            check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
            secret = hmac.new(b"WebAppData", app.TOKEN.encode(), hashlib.sha256).digest()
            fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
            signed = urllib.parse.urlencode(fields)
            self.assertEqual(app.authenticate(signed), 77)
            with self.assertRaises(ValueError):
                app.authenticate(signed.replace("77", "78"))
            fields["auth_date"] = str(int(time.time()) - 90000)
            with self.assertRaises(ValueError):
                app.authenticate(urllib.parse.urlencode(fields))
        finally:
            app.TOKEN = old_token

    def test_local_preview_with_loaded_token(self):
        old_dev, old_token = app.DEV, app.TOKEN
        try:
            app.DEV, app.TOKEN = True, "123:local"
            self.assertEqual(app.authenticate("dev"), 1)
            app.DEV = False
            with self.assertRaises(ValueError):
                app.authenticate("dev")
        finally:
            app.DEV, app.TOKEN = old_dev, old_token


if __name__ == "__main__":
    unittest.main()
