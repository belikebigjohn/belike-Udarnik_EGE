"""Server-owned learning sessions, rewards and additive SQLite migrations."""
import hashlib
import json
import os
import random
import secrets
import unicodedata
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATEGORIES = {'paronyms': 'Редактор в эфире', 'speech': 'Ляп в прямом эфире',
              'spelling': 'Пропущенный сигнал', 'punctuation': 'Расставь паузы'}
RANKS = [(0, 'Стажёр'), (100, 'Корреспондент'), (300, 'Младший ведущий'),
         (700, 'Ведущий эфира'), (1500, 'Старший ведущий'), (3000, 'Шеф-редактор'),
         (6000, 'Звезда телеканала'), (10000, 'Легенда эфира')]
ACHIEVEMENTS = {'first': ('Первый эфир', 20), 'ten': ('Десять подряд', 30),
    'perfect': ('Идеальный выпуск', 30), 'week': ('Семь дней занятий', 50),
    'hundred': ('Сто изученных заданий', 100), 'stress': ('Мастер ударений', 50),
    'paronyms': ('Гроза паронимов', 50)}

def now():
    return datetime.now(timezone.utc)

def normalize(value):
    # Ё remains distinct. Do not erase punctuation or internal spaces.
    return ' '.join(unicodedata.normalize('NFC', value).casefold().strip().split())

def validate_questions(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Нужен непустой список заданий')
    seen, prompts = set(), set()
    for q in rows:
        required = ('id','category','topic','type','prompt','difficulty','answer','alternatives','explanation','source','format')
        if not isinstance(q,dict) or any(k not in q for k in required):
            raise ValueError('Неполная запись задания')
        if any(not isinstance(q[k],str) or not q[k].strip() for k in ('id','topic','prompt','explanation','source')):
            raise ValueError('Пустые текстовые поля')
        if q['id'] in seen or q['prompt'] in prompts:
            raise ValueError('Дубликат задания: '+q['id'])
        seen.add(q['id']); prompts.add(q['prompt'])
        if q['category'] not in CATEGORIES or type(q['difficulty']) is not int or q['difficulty'] not in (1,2,3):
            raise ValueError('Некорректная категория или сложность')
        if urlparse(q['source']).scheme!='https' or not urlparse(q['source']).netloc:
            raise ValueError('Источник должен быть HTTPS-ссылкой')
        if q['format']=='ege':
            numbers={'paronyms':{5},'speech':{6,7},'spelling':set(range(9,16)),'punctuation':set(range(16,22))}
            if type(q.get('exam_number')) is not int or q['exam_number'] not in numbers[q['category']]:
                raise ValueError('Проверьте номер задания ЕГЭ')
        if q['format'] not in ('learn','ege') or not isinstance(q['alternatives'],list):
            raise ValueError('Некорректный формат')
        if q['type'] in ('choice','text'):
            if not isinstance(q['answer'],str) or not q['answer'] or any(not isinstance(a,str) for a in q['alternatives']):
                raise ValueError('Некорректный ответ')
            if q['type']=='choice' and (not isinstance(q.get('options'),list) or len(q['options'])<2 or any(not isinstance(a,str) for a in q['options']) or q['answer'] not in q['options'] or len(q['options'])!=len(set(q['options']))):
                raise ValueError('Проверьте варианты ответа')
        elif q['type'] in ('commas','numbers'):
            count = len(q.get('tokens',[]))-1 if q['type']=='commas' else len(q.get('options',[]))
            if count<1 or not isinstance(q['answer'],list) or any(type(n) is not int or n<1 or n>count for n in q['answer']) or len(q['answer'])!=len(set(q['answer'])) or q['alternatives']:
                raise ValueError('Некорректные позиции')
            items = q.get('tokens') if q['type']=='commas' else q.get('options')
            if any(not isinstance(s,str) or not s for s in items):
                raise ValueError('Некорректные элементы предложения')
        else:
            raise ValueError('Неизвестный тип')
    return rows

def catalog(words):
    rows = validate_questions(json.loads((ROOT/'data/questions.json').read_text(encoding='utf-8-sig')))
    result = {q['id']:q for q in rows}
    for w in words.values():
        result['stress:'+w['id']] = dict(id='stress:'+w['id'],category='stress',topic='Ударения',type='stress',
            prompt=w['form'],note=w['note'],answer=w['stress_index'],marked=w['marked'],difficulty=2 if len(w['form'])>=10 else 1,
            alternatives=[],explanation='Правильное ударение: '+w['marked']+('. '+w['note'] if w['note'] else ''),
            source='https://doc.fipi.ru/navigator-podgotovki/navigator-ege/2026/ru-1-fonetika.pdf',format='learn')
    return result

def migrate(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS learning_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS learning_sessions(
      id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,mode TEXT NOT NULL,queue TEXT NOT NULL,
      position INTEGER NOT NULL DEFAULT 0,lives INTEGER NOT NULL DEFAULT 3,outcomes TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL,question_at TEXT NOT NULL,seconds INTEGER NOT NULL DEFAULT 0,
      day TEXT NOT NULL,finished INTEGER NOT NULL DEFAULT 0,best_chain INTEGER NOT NULL DEFAULT 0,chain INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS learning_active ON learning_sessions(user_id,finished);
    CREATE TABLE IF NOT EXISTS learning_answers(
      id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,question_id TEXT NOT NULL,category TEXT NOT NULL,
      correct INTEGER NOT NULL,answered_at TEXT NOT NULL,mode TEXT NOT NULL,xp INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS learning_history ON learning_answers(user_id,answered_at);
    CREATE TABLE IF NOT EXISTS learning_progress(
      user_id INTEGER NOT NULL,question_id TEXT NOT NULL,successes INTEGER NOT NULL DEFAULT 0,
      mistakes INTEGER NOT NULL DEFAULT 0,last_day TEXT,due_at TEXT NOT NULL,PRIMARY KEY(user_id,question_id));
    CREATE TABLE IF NOT EXISTS learning_rewards(
      user_id INTEGER NOT NULL,reward_key TEXT NOT NULL,xp INTEGER NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(user_id,reward_key));
    CREATE TABLE IF NOT EXISTS learning_achievements(
      user_id INTEGER NOT NULL,achievement TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(user_id,achievement));
    CREATE TABLE IF NOT EXISTS learning_daily(
      user_id INTEGER NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,session_id TEXT NOT NULL,PRIMARY KEY(user_id,day,kind));
    INSERT OR IGNORE INTO learning_migrations VALUES(1,CURRENT_TIMESTAMP);
    """)

def award(conn,uid,key,amount):
    inserted=conn.execute('INSERT OR IGNORE INTO learning_rewards VALUES(?,?,?,?)',(uid,key,amount,now().isoformat())).rowcount
    return amount if inserted else 0

def activity_streak(conn,uid):
    days={r[0] for r in conn.execute('SELECT DISTINCT substr(answered_at,1,10) FROM learning_answers WHERE user_id=?',(uid,))}
    cursor=now().date()
    if cursor.isoformat() not in days:
        cursor-=timedelta(days=1)
    count=0
    while cursor.isoformat() in days:
        count+=1; cursor-=timedelta(days=1)
    return count

def unlock(conn,uid,perfect=False):
    rows=conn.execute('SELECT question_id,category,correct FROM learning_answers WHERE user_id=? ORDER BY id',(uid,)).fetchall()
    unique={r['question_id'] for r in rows if r['correct']}
    chain=best=0
    for r in rows:
        chain=chain+1 if r['correct'] else 0
        best=max(best,chain)
    checks={'first':bool(rows),'ten':best>=10,'perfect':perfect,'week':activity_streak(conn,uid)>=7,
       'hundred':len(unique)>=100,
       'stress':len({r['question_id'] for r in rows if r['correct'] and r['category']=='stress'})>=30,
       'paronyms':len({r['question_id'] for r in rows if r['correct'] and r['category']=='paronyms'})>=10}
    earned=[]
    for key,ok in checks.items():
        if ok and conn.execute('INSERT OR IGNORE INTO learning_achievements VALUES(?,?,?)',(uid,key,now().isoformat())).rowcount:
            title,xp=ACHIEVEMENTS[key]
            award(conn,uid,'achievement:'+key,xp)
            earned.append(dict(id=key,title=title,xp=xp))
    return earned

def record(conn,uid,qid,category,correct,mode):
    stamp=now(); day=stamp.date().isoformat()
    old=conn.execute('SELECT * FROM learning_progress WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()
    successes=old['successes'] if old else 0
    mistakes=(old['mistakes'] if old else 0)+int(not correct)
    last_day=old['last_day'] if old else None
    if not correct:
        successes=0; due=stamp+timedelta(days=1)
    elif last_day!=day:
        successes+=1; last_day=day
        due=stamp+timedelta(days=(1,3,7,14)[min(successes-1,3)])
    else:
        due=datetime.fromisoformat(old['due_at'])
    conn.execute("""INSERT INTO learning_progress VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,question_id)
        DO UPDATE SET successes=excluded.successes,mistakes=excluded.mistakes,last_day=excluded.last_day,due_at=excluded.due_at""",
        (uid,qid,successes,mistakes,last_day,due.isoformat()))
    if qid.startswith('stress:') and mode not in ('round','ege'):
        conn.execute('''INSERT INTO progress(user_id,word_id,attempts,mistakes,streak_days,last_correct_day,due_at)
            VALUES(?,?,1,?,?,?,?) ON CONFLICT(user_id,word_id) DO UPDATE SET
            attempts=progress.attempts+1,mistakes=excluded.mistakes,streak_days=excluded.streak_days,
            last_correct_day=excluded.last_correct_day,due_at=excluded.due_at''',
            (uid,qid[7:],mistakes,successes,last_day,due.isoformat()))
    xp=award(conn,uid,'answer:'+day+':'+qid,10) if correct else 0
    conn.execute('INSERT INTO learning_answers(user_id,question_id,category,correct,answered_at,mode,xp) VALUES(?,?,?,?,?,?,?)',
        (uid,qid,category,int(correct),stamp.isoformat(),mode,xp))
    count=conn.execute('SELECT COUNT(DISTINCT question_id) FROM learning_answers WHERE user_id=? AND substr(answered_at,1,10)=?',(uid,day)).fetchone()[0]
    if count>=10:
        xp+=award(conn,uid,'goal:'+day,30)
    return xp

def sync_legacy(conn,uid):
    marker='migration:legacy-v1'
    if conn.execute('SELECT 1 FROM learning_rewards WHERE user_id=? AND reward_key=?',(uid,marker)).fetchone():
        return
    for r in conn.execute('SELECT * FROM answers WHERE user_id=? ORDER BY id',(uid,)).fetchall():
        conn.execute('INSERT INTO learning_answers(user_id,question_id,category,correct,answered_at,mode) VALUES(?,?,?,?,?,?)',
            (uid,'stress:'+r['word_id'],'stress',r['correct'],r['answered_at'],r['mode']))
    for r in conn.execute('SELECT * FROM progress WHERE user_id=?',(uid,)).fetchall():
        conn.execute('INSERT OR IGNORE INTO learning_progress VALUES(?,?,?,?,?,?)',
            (uid,'stress:'+r['word_id'],r['streak_days'],r['mistakes'],r['last_correct_day'],r['due_at']))
    award(conn,uid,marker,0)

def rank(xp):
    index=max(i for i,(threshold,_) in enumerate(RANKS) if xp>=threshold)
    return dict(name=RANKS[index][1],level=index+1,start=RANKS[index][0],next=RANKS[index+1][0] if index+1<len(RANKS) else None)

def dashboard(conn,uid,questions):
    stamp=now(); day=stamp.date().isoformat()
    xp=conn.execute('SELECT COALESCE(SUM(xp),0) FROM learning_rewards WHERE user_id=?',(uid,)).fetchone()[0]
    today=conn.execute('SELECT COUNT(*) total,COALESCE(SUM(correct),0) correct,COUNT(DISTINCT question_id) unique_count FROM learning_answers WHERE user_id=? AND substr(answered_at,1,10)=?',(uid,day)).fetchone()
    total=conn.execute('SELECT COUNT(*) total,COALESCE(SUM(correct),0) correct,COUNT(DISTINCT CASE WHEN correct=1 THEN question_id END) studied FROM learning_answers WHERE user_id=?',(uid,)).fetchone()
    week=[]
    for offset in reversed(range(7)):
        d=(stamp.date()-timedelta(days=offset)).isoformat()
        r=conn.execute('SELECT COUNT(*) total,COALESCE(SUM(correct),0) correct FROM learning_answers WHERE user_id=? AND substr(answered_at,1,10)=?',(uid,d)).fetchone()
        week.append(dict(day=d,total=r['total'],correct=r['correct']))
    due=conn.execute('SELECT COUNT(*) FROM learning_progress WHERE user_id=? AND due_at<=?',(uid,stamp.isoformat())).fetchone()[0]
    earned={r[0] for r in conn.execute('SELECT achievement FROM learning_achievements WHERE user_id=?',(uid,))}
    records={mode:conn.execute('SELECT COALESCE(MAX(best_chain),0) FROM learning_sessions WHERE user_id=? AND mode=? AND finished=1',(uid,mode)).fetchone()[0] for mode in ('survival','teleprompter')}
    daily={r['kind']:r['session_id'] for r in conn.execute('SELECT kind,session_id FROM learning_daily WHERE user_id=? AND day=?',(uid,day))}
    archive=[]
    for r in conn.execute("SELECT d.day,s.queue,s.outcomes FROM learning_daily d JOIN learning_sessions s ON s.id=d.session_id WHERE d.user_id=? AND d.kind='word' AND s.finished=1 ORDER BY d.day DESC LIMIT 30",(uid,)):
        q=questions.get(json.loads(r['queue'])[0])
        if q:
            archive.append(dict(day=r['day'],word=q.get('marked',q['prompt']),correct=json.loads(r['outcomes'])[0]['correct']))
    exam=None
    configured=os.getenv('EGE_DATE','')
    if configured:
        try:
            exam_day=date.fromisoformat(configured)
            exam=dict(date=configured,days=(exam_day-stamp.date()).days,official=os.getenv('EGE_DATE_OFFICIAL')=='1')
        except ValueError:
            exam=dict(error='Проверьте EGE_DATE: нужен формат YYYY-MM-DD')
    best_today=conn.execute('SELECT COALESCE(MAX(best_chain),0) FROM learning_sessions WHERE user_id=? AND day=?',(uid,day)).fetchone()[0]
    return dict(xp=xp,rank=rank(xp),today=dict(today),total=dict(total),streak=activity_streak(conn,uid),
        week=week,due=due,records=records,daily=daily,archive=archive,exam=exam,goal=10,best_today=best_today,
        achievements=[dict(id=k,title=v[0],xp=v[1],earned=k in earned) for k,v in ACHIEVEMENTS.items()],
        categories=[dict(id=k,title=v,count=sum(q['category']==k for q in questions.values()),
            topics=sorted({q['topic'] for q in questions.values() if q['category']==k and q['format']=='learn'})) for k,v in CATEGORIES.items()],
        active=[dict(id=r['id'],mode=r['mode']) for r in conn.execute('SELECT id,mode FROM learning_sessions WHERE user_id=? AND finished=0 ORDER BY created_at DESC LIMIT 10',(uid,))])

def public_question(q):
    return {k:v for k,v in q.items() if k not in ('answer','alternatives','explanation','marked','source','exam_data')}

def session_view(conn,uid,sid,questions):
    r=conn.execute('SELECT * FROM learning_sessions WHERE id=? AND user_id=?',(sid,uid)).fetchone()
    if not r:
        raise ValueError('Эфир не найден')
    queue=json.loads(r['queue']); outcomes=json.loads(r['outcomes'])
    correct=sum(o['correct'] for o in outcomes)
    result=dict(id=sid,mode=r['mode'],category=questions[queue[0]]['category'],level={12:'beginner',8:'host',5:'pro'}.get(r['seconds'],'beginner'),position=r['position']+1,total=len(queue),lives=r['lives'],finished=bool(r['finished']),
        outcomes=[{k:o[k] for k in ('question_id','correct','xp')} for o in outcomes],correct=correct,best_chain=r['best_chain'],xp=sum(o['xp'] for o in outcomes),
        accuracy=round(100*correct/len(outcomes)) if outcomes else 0,started_at=r['created_at'],server_now=now().isoformat())
    if r['finished'] and r['mode']=='teleprompter':
        mistakes=[]
        for position,outcome in enumerate(outcomes,1):
            if outcome['correct']:
                continue
            review=outcome.get('review')
            if review is None:
                # Existing sessions predate answer snapshots: recover the question,
                # but never invent the user's answer or a timeout reason.
                q=questions[outcome['question_id']]
                review=dict(question=public_question(q),answer=q.get('marked',q['answer']),
                    explanation=q['explanation'],source=q['source'])
            mistakes.append(dict(review,position=position))
        result['mistakes']=mistakes
    if not r['finished']:
        result['question']=public_question(questions[queue[r['position']]])
        result['deadline']=(datetime.fromisoformat(r['question_at'])+timedelta(seconds=r['seconds'])).isoformat() if r['seconds'] else None
    return result

def start(conn,uid,payload,questions):
    mode=payload.get('mode','practice'); category=payload.get('category')
    if mode not in ('practice','ege','survival','teleprompter','review','emergency','word'):
        raise ValueError('Неизвестный режим')
    if mode in ('practice','ege') and category not in CATEGORIES:
        raise ValueError('Выберите рубрику')
    day=now().date().isoformat()
    if mode in ('word','emergency'):
        existing=conn.execute('SELECT session_id FROM learning_daily WHERE user_id=? AND day=? AND kind=?',(uid,day,mode)).fetchone()
        if existing:
            return session_view(conn,uid,existing[0],questions)
    topic=payload.get('topic','')
    pool=[q for q in questions.values() if q['format']=='learn' and q['category']!='exam']
    if mode in ('practice','ege'):
        pool=[q for q in questions.values() if q['category']==category and q['format']==('ege' if mode=='ege' else 'learn') and (not topic or q['topic']==topic)]
    elif mode=='review':
        due={r[0] for r in conn.execute('SELECT question_id FROM learning_progress WHERE user_id=? AND due_at<=? ORDER BY mistakes DESC,due_at',(uid,now().isoformat()))}
        pool=[q for q in questions.values() if q['id'] in due]
        if not pool:
            raise ValueError('Повторений на сегодня нет. Возвращайся завтра или открой другую рубрику.')
    elif mode=='emergency':
        pool=[q for q in pool if q['difficulty']>=2]
    elif mode=='word':
        pool=[q for q in pool if q['type']=='stress']
    if not pool:
        raise ValueError('В этой теме пока нет проверенных заданий')
    if mode in ('word','emergency'):
        pool.sort(key=lambda q:q['id'])
        offset=int(hashlib.sha256(mode.encode()).hexdigest()[:8],16)
        selected=[pool[(now().date().toordinal()+offset)%len(pool)]['id']]
    else:
        progress={r['question_id']:r for r in conn.execute('SELECT * FROM learning_progress WHERE user_id=?',(uid,))}
        random.shuffle(pool)
        pool.sort(key=lambda q:(0 if q['id'] in progress and progress[q['id']]['due_at']<=now().isoformat() else 1 if q['id'] not in progress else 2,
                                 -progress[q['id']]['mistakes'] if q['id'] in progress else 0))
        selected=[q['id'] for q in pool[:10 if mode=='teleprompter' else 5]]
    level=payload.get('level','beginner')
    if level not in ('beginner','host','pro'):
        raise ValueError('Неизвестная скорость')
    seconds=10 if mode=='emergency' else {'beginner':12,'host':8,'pro':5}[level] if mode=='teleprompter' else 0
    sid=secrets.token_urlsafe(18); stamp=now().isoformat()
    conn.execute('INSERT INTO learning_sessions(id,user_id,mode,queue,created_at,question_at,seconds,day) VALUES(?,?,?,?,?,?,?,?)',
        (sid,uid,mode,json.dumps(selected),stamp,stamp,seconds,day))
    if mode in ('word','emergency'):
        conn.execute('INSERT INTO learning_daily VALUES(?,?,?,?)',(uid,day,mode,sid))
    return session_view(conn,uid,sid,questions)

def check(q,value):
    if q['type']=='exam':
        import exam
        return exam.score(q['exam_data'],value)==exam.RULES[q['exam_number']]['max_score']
    if q['type'] in ('choice','text'):
        if not isinstance(value,str) or len(value)>250:
            raise ValueError('Введите ответ')
        if q['type']=='choice' and value not in q['options']:
            raise ValueError('Выберите предложенный вариант')
        return normalize(value) in {normalize(a) for a in [q['answer']]+q['alternatives']}
    if q['type']=='stress':
        if type(value) is not int or not 0<=value<len(q['prompt']) or q['prompt'][value] not in 'аеёиоуыэюя':
            raise ValueError('Выберите гласную')
        return value==q['answer']
    maximum=len(q['tokens'])-1 if q['type']=='commas' else len(q['options'])
    if not isinstance(value,list) or any(type(n) is not int or not 1<=n<=maximum for n in value) or len(set(value))!=len(value):
        raise ValueError('Выберите позиции без повторов')
    return sorted(value)==sorted(q['answer'])

def answer(conn,uid,payload,questions):
    r=conn.execute('SELECT * FROM learning_sessions WHERE id=? AND user_id=?',(payload.get('session_id'),uid)).fetchone()
    if not r or r['finished']:
        raise ValueError('Эфир уже завершён')
    if type(payload.get('position')) is not int or payload['position']!=r['position']+1:
        raise ValueError('Карточка уже отвечена — обнови эфир')
    q=questions[json.loads(r['queue'])[r['position']]]
    expired=bool(r['seconds'] and (now()-datetime.fromisoformat(r['question_at'])).total_seconds()>=r['seconds'])
    if payload.get('timeout') and not expired:
        raise ValueError('Время ещё не истекло')
    correct=False if expired else check(q,payload.get('answer'))
    if q['type']=='exam':
        import exam
        graded=exam.record(conn,uid,'srs:'+r['id'],q['exam_data'],payload.get('answer',''),unlock_rewards=False)
        xp=graded['xp']
    else:
        xp=record(conn,uid,q['id'],q['category'],correct,r['mode'])
    lives=r['lives']-int(not correct) if r['mode']=='survival' else r['lives']
    chain=r['chain']+1 if correct else 0; best=max(chain,r['best_chain'])
    outcomes=json.loads(r['outcomes'])
    previous=conn.execute('SELECT COALESCE(MAX(best_chain),0) FROM learning_sessions WHERE user_id=? AND mode=? AND finished=1',(uid,r['mode'])).fetchone()[0]
    done=r['position']+1>=len(json.loads(r['queue'])) or lives<=0
    if correct and r['mode']=='emergency':
        xp+=award(conn,uid,'emergency:'+r['day'],40)
    if done and r['mode']=='survival' and all(o['correct'] for o in outcomes) and correct:
        xp+=award(conn,uid,'perfect:'+r['day'],30)
    earned=unlock(conn,uid,perfect=done and len(outcomes)>=4 and correct and all(o['correct'] for o in outcomes))
    xp+=sum(a['xp'] for a in earned)
    outcome=dict(question_id=q['id'],correct=correct,xp=xp)
    if r['mode']=='teleprompter' and not correct:
        outcome['review']=dict(question=public_question(q),answer=q.get('marked',q['answer']),
            chosen=payload.get('answer'),expired=expired,explanation=q['explanation'],source=q['source'])
    outcomes.append(outcome)
    conn.execute('UPDATE learning_sessions SET position=position+1,lives=?,outcomes=?,finished=?,question_at=?,chain=?,best_chain=? WHERE id=?',
        (lives,json.dumps(outcomes),int(done),now().isoformat(),chain,best,r['id']))
    state=session_view(conn,uid,r['id'],questions)
    feedback=dict(correct=correct,expired=expired,answer=q.get('marked',q['answer']),explanation=q['explanation'],
        source=q['source'],xp=xp,achievements=earned,new_record=done and best>previous)
    if q['type']=='commas':
        chosen=payload.get('answer') if isinstance(payload.get('answer'),list) else []
        feedback.update(missing=sorted(set(q['answer'])-set(chosen)),extra=sorted(set(chosen)-set(q['answer'])))
    return dict(session=state,feedback=feedback)

