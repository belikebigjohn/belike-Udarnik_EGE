"""Exam 2027 bank, strict grading, persistent drafts and shared learning rewards."""
import csv
import hashlib
import json
import random
import re
import secrets
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse
import learning

ROOT=Path(__file__).resolve().parent
SPEC_URL='https://fipi.ru/ege/demoversii-specifikacii-kodifikatory'
TITLES={4:'Ударения',5:'Паронимы',6:'Лексические нормы',7:'Формы слов',
8:'Синтаксические нормы',9:'Корни',10:'Приставки, Ъ и Ь',11:'Суффиксы',
12:'Глаголы и причастия',13:'НЕ и НИ',14:'Слитно, раздельно, дефис',15:'Н и НН',
16:'Однородные члены и сложные предложения',17:'Обособление',
18:'Вводные слова и обращения',19:'Сложное предложение',20:'Разные виды связи',
21:'Пунктуационный анализ'}
UNORDERED={4,*range(9,22)}
RULES={n:dict(title=title,max_score=2 if n==8 else 1,
    rule='positions' if n==8 else 'unordered' if n in UNORDERED else 'exact')
    for n,title in TITLES.items()}

def validate_bank(rows):
    errors=[]; ids=set(); fingerprints=set()
    if not isinstance(rows,list):
        raise ValueError('Банк должен быть JSON-массивом')
    for i,q in enumerate(rows,1):
        try:
            required=('id','subject','year','number','type','prompt','text','options','answer','alternatives',
                'explanation','source','source_url','source_id','origin','rights','checked_at','difficulty','status','checking')
            if not isinstance(q,dict) or any(k not in q for k in required): raise ValueError('Неполная структура')
            if not isinstance(q['id'],str) or not re.fullmatch(r'[a-zA-Z0-9:_-]{1,100}',q['id']): raise ValueError('Некорректный ID')
            if q['id'] in ids: raise ValueError('Повтор ID')
            ids.add(q['id'])
            if q['subject']!='russian' or type(q['year']) is not int or q['year']!=2027: raise ValueError('Поддерживается русский язык, спецификация 2027')
            n=q['number']
            if type(n) is not int or n not in RULES: raise ValueError('Поддерживаются только номера 4–21')
            if q['type'] not in ('text','digits','multi','matching'): raise ValueError('Неизвестный тип')
            if any(not isinstance(q[k],str) for k in ('prompt','text','answer','explanation','source','source_url','source_id','checking')): raise ValueError('Проверьте текстовые поля')
            if not q['prompt'].strip() or len(q['prompt'])>20000 or len(q['text'])>50000: raise ValueError('Пустое или слишком длинное условие')
            if not isinstance(q['options'],list) or any(not isinstance(o,str) or not o for o in q['options']) or len(q['options'])>9: raise ValueError('Некорректные варианты')
            if len(q['options'])!=len(set(q['options'])): raise ValueError('Повтор вариантов')
            if not isinstance(q['alternatives'],list) or any(not isinstance(a,str) or not a for a in q['alternatives']): raise ValueError('Некорректные альтернативы')
            if q['checking']!=RULES[n]['rule']: raise ValueError('Правило проверки не соответствует номеру')
            if q['type']=='matching':
                if n!=8 or not isinstance(q.get('left'),list) or len(q['left'])!=5 or any(not isinstance(x,str) or not x for x in q['left']) or len(q['options'])!=9: raise ValueError('Соответствие: 5 элементов и 9 вариантов')
            elif n==8: raise ValueError('Нужен тип matching')
            if n in (5,6,7) and q['type']!='text': raise ValueError('Для этого номера нужен текстовый ответ')
            if n not in (5,6,7) and q['type']=='text': raise ValueError('Для этого номера нужен цифровой ответ')
            if q['type']=='multi' and not q['options']: raise ValueError('Нет вариантов выбора')
            if q['text'].strip() or q.get('text_id'): raise ValueError('Задания с исходным текстом исключены')
            if q['type']!='text':
                for a in [q['answer']]+q['alternatives']:
                    if not a and q['status']!='published': continue
                    if not re.fullmatch('[1-9]+',a): raise ValueError('Ответ должен состоять из цифр 1–9')
                    if q['type'] in ('multi','matching') and any(int(c)>len(q['options']) for c in a): raise ValueError('Ответ вне вариантов')
                    if q['type']=='matching' and len(a)!=5: raise ValueError('В соответствии должно быть 5 позиций')
                    if q['checking']=='unordered' and len(a)!=len(set(a)): raise ValueError('Дубли в эталоне')
            if q['origin'] not in ('authored','fipi','sdamgia','other'): raise ValueError('Неизвестное происхождение')
            if not isinstance(q['rights'],dict) or q['rights'].get('status') not in ('own','permission','public_domain','unknown'): raise ValueError('Нужен статус прав')
            if q['origin']!='authored' and q['rights']['status']=='own': raise ValueError('Чужое задание не может иметь собственные права')
            if q['origin']=='authored' and q['rights']['status']!='own': raise ValueError('Проверьте права авторского задания')
            if q['status'] not in ('draft','published','archived'): raise ValueError('Неизвестный статус публикации')
            if type(q['difficulty']) is not int or q['difficulty'] not in (1,2,3): raise ValueError('Сложность 1–3')
            if q['status']=='published':
                if not q['answer'] or not q['explanation'].strip(): raise ValueError('Без ответа и объяснения публикация запрещена')
                if q['rights']['status']=='unknown' or not q['rights'].get('evidence'): raise ValueError('Нет основания использования')
                if date.fromisoformat(q['checked_at'])>date.today(): raise ValueError('Дата проверки в будущем')
                if urlparse(q['source_url']).scheme!='https' or not urlparse(q['source_url']).netloc: raise ValueError('Источник должен быть HTTPS')
            key=hashlib.sha256(json.dumps([n,q['prompt'],q['text'],q['options']],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if key in fingerprints: raise ValueError('Дубликат содержания')
            fingerprints.add(key)
        except (ValueError,TypeError,KeyError) as exc:
            errors.append(dict(row=i,id=q.get('id') if isinstance(q,dict) else None,error=str(exc)))
    if errors:
        raise ValueError(json.dumps(errors,ensure_ascii=False))
    return rows

def load_bank(path=None):
    rows=validate_bank(json.loads((path or ROOT/'data/exam_questions.json').read_text(encoding='utf-8-sig')))
    return {q['id']:q for q in rows if q['status']=='published'}

def migrate(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS exam_sessions(
      id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,mode TEXT NOT NULL,questions TEXT NOT NULL,
      drafts TEXT NOT NULL DEFAULT '{}',results TEXT NOT NULL DEFAULT '{}',position INTEGER NOT NULL DEFAULT 0,
      revision INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,deadline TEXT,finished INTEGER NOT NULL DEFAULT 0,
      reveal TEXT NOT NULL,label TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS exam_active ON exam_sessions(user_id,finished);
    CREATE TABLE IF NOT EXISTS exam_attempts(
      id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,session_id TEXT NOT NULL,question_id TEXT NOT NULL,
      number INTEGER NOT NULL,chosen TEXT NOT NULL,score INTEGER NOT NULL,max_score INTEGER NOT NULL,
      correct INTEGER NOT NULL,answered_at TEXT NOT NULL,xp INTEGER NOT NULL,
      UNIQUE(session_id,question_id));
    CREATE INDEX IF NOT EXISTS exam_user ON exam_attempts(user_id,number);
    INSERT OR IGNORE INTO learning_migrations VALUES(2,CURRENT_TIMESTAMP);
    """)

def normalize(value):
    if not isinstance(value,str) or len(value)>250: raise ValueError('Ответ должен быть строкой до 250 символов')
    # Exam forms do not permit spaces, punctuation or separators in the answer.
    # Strip outer whitespace only; ё is not silently replaced by е.
    return learning.normalize(value)

def score(q,value):
    value=normalize(value)
    references=[normalize(a) for a in [q['answer']]+q['alternatives']]
    rule=q['checking']; maximum=RULES[q['number']]['max_score']
    if rule=='unordered':
        if not re.fullmatch(r'[1-9]+',value) or len(set(value))!=len(value): return 0
        return maximum if any(sorted(value)==sorted(a) for a in references) else 0
    if rule=='positions':
        # A zero represents an unfilled matching slot in saved UI drafts.
        # It counts as one incorrect position rather than erasing other answers.
        if not re.fullmatch(r'[0-9]+',value): return 0
        best=0
        for a in references:
            if len(value)>len(a): continue
            # Missing trailing positions count as wrong positions, as specified.
            wrong=sum(i>=len(value) or value[i]!=c for i,c in enumerate(a))
            best=max(best,2 if wrong==0 else 1 if wrong in (1,2) else 0)
        return best
    return maximum if value in references else 0

def snapshot(q):
    hidden={'answer','alternatives','explanation','rights','source_url','source_id','checking'}
    return {k:v for k,v in q.items() if k not in hidden}

def row_for(conn,uid,sid):
    r=conn.execute('SELECT * FROM exam_sessions WHERE id=? AND user_id=?',(sid,uid)).fetchone()
    if not r: raise ValueError('Тренировка не найдена')
    if not session_in_scope(r): raise ValueError('Этот вариант больше не входит в тематическую практику')
    return r

def session_in_scope(row):
    return all(q.get('number') in RULES and not q.get('text') for q in json.loads(row['questions']))

def expired(r):
    return bool(r['deadline'] and learning.now().isoformat()>=r['deadline'])

def record(conn,uid,sid,q,chosen,unlock_rewards=True):
    points=score(q,chosen); maximum=RULES[q['number']]['max_score']; correct=points==maximum
    xp=learning.record(conn,uid,'exam:'+q['id'],'exam',correct,'exam')
    earned=learning.unlock(conn,uid) if unlock_rewards else []
    xp+=sum(a['xp'] for a in earned)
    conn.execute('INSERT INTO exam_attempts(user_id,session_id,question_id,number,chosen,score,max_score,correct,answered_at,xp) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (uid,sid,q['id'],q['number'],chosen,points,maximum,int(correct),learning.now().isoformat(),xp))
    return dict(chosen=chosen,score=points,max_score=maximum,correct=correct,xp=xp,answer=q['answer'],
        alternatives=q['alternatives'],explanation=q['explanation'],source=q['source'],source_url=q['source_url'])

def finish(conn,uid,sid):
    r=row_for(conn,uid,sid)
    if r['finished']: return
    qs=json.loads(r['questions']); drafts=json.loads(r['drafts']); results=json.loads(r['results'])
    for q in qs:
        if q['id'] not in results: results[q['id']]=record(conn,uid,sid,q,drafts.get(q['id'],''))
    conn.execute('UPDATE exam_sessions SET finished=1,results=?,revision=revision+1 WHERE id=?',(json.dumps(results,ensure_ascii=False),sid))

def session_view(conn,uid,sid):
    r=row_for(conn,uid,sid)
    if not r['finished'] and expired(r):
        finish(conn,uid,sid);r=row_for(conn,uid,sid)
    qs=json.loads(r['questions']); drafts=json.loads(r['drafts']); results=json.loads(r['results'])
    visible=results if r['finished'] or r['reveal']=='immediate' else {}
    return dict(id=sid,mode=r['mode'],label=r['label'],position=r['position'],revision=r['revision'],
        questions=[dict(snapshot(q),result=visible.get(q['id']),draft=drafts.get(q['id'],'')) for q in qs],
        finished=bool(r['finished']),deadline=r['deadline'],server_now=learning.now().isoformat(),reveal=r['reveal'],
        answered=list(results),total=len(qs),correct=sum(v['correct'] for v in results.values()) if r['finished'] else None,
        points=sum(v['score'] for v in results.values()) if r['finished'] else None,
        max_points=sum(RULES[q['number']]['max_score'] for q in qs),
        xp=sum(v['xp'] for v in results.values()) if r['finished'] else None)

def question_stats(conn,uid):
    rows=conn.execute('SELECT * FROM exam_attempts WHERE user_id=? ORDER BY id',(uid,)).fetchall()
    by={}
    for row in rows: by.setdefault(row['question_id'],[]).append(row)
    return by,rows

def qualifies(history,filter_):
    if filter_=='unseen': return not history
    if filter_=='mistakes': return bool(history and not history[-1]['correct'])
    if filter_=='mastered':
        days=set()
        for row in reversed(history):
            if not row['correct']: break
            days.add(row['answered_at'][:10])
        return len(days)>=3
    return True

def dashboard(conn,uid,bank):
    by,rows=question_stats(conn,uid); numbers=[]
    by={qid:history for qid,history in by.items() if qid in bank}
    rows=[r for r in rows if r['question_id'] in bank]
    for n in RULES:
        qs=[q for q in bank.values() if q['number']==n]; ids={q['id'] for q in qs}
        attempts=[r for r in rows if r['question_id'] in ids]
        correct=sum(r['correct'] for r in attempts)
        filters={f:sum(qualifies(by.get(q['id'],[]),f) for q in qs) for f in ('all','unseen','mistakes','mastered')}
        numbers.append(dict(number=n,**RULES[n],count=len(qs),solved=sum(q['id'] in by for q in qs),
            attempts=len(attempts),accuracy=round(100*correct/len(attempts)) if attempts else None,
            filters=filters,authored=sum(q['origin']=='authored' for q in qs),
            original=sum(q['origin']!='authored' for q in qs),
            state='mastered' if qs and filters['mastered']==len(qs) else 'review' if filters['mistakes'] else 'learning' if attempts else 'new'))
    active=[dict(id=r['id'],label=r['label']) for r in conn.execute('SELECT id,label,questions FROM exam_sessions WHERE user_id=? AND finished=0 ORDER BY created_at DESC LIMIT 20',(uid,)) if session_in_scope(r)]
    history=[dict(id=r['id'],label=r['label'],created_at=r['created_at']) for r in conn.execute('SELECT id,label,created_at,questions FROM exam_sessions WHERE user_id=? AND finished=1 ORDER BY created_at DESC LIMIT 30',(uid,)) if session_in_scope(r)]
    week=[]
    for offset in reversed(range(7)):
        day=(learning.now().date()-timedelta(days=offset)).isoformat(); daily=[r for r in rows if r['answered_at'][:10]==day]
        week.append(dict(day=day,total=len(daily),accuracy=round(100*sum(r['correct'] for r in daily)/len(daily)) if daily else None))
    topics=[x for x in numbers if x['attempts']>=3]
    return dict(numbers=numbers,active=active,history=history,total=len(rows),solved=len(by),
        accuracy=round(100*sum(r['correct'] for r in rows)/len(rows)) if rows else None,
        mistakes=sum(not hist[-1]['correct'] for hist in by.values()),week=week,
        strongest=sorted([x for x in topics if x['accuracy']>=80],key=lambda x:-x['accuracy'])[:3],
        weakest=sorted([x for x in topics if x['accuracy']<80],key=lambda x:x['accuracy'])[:3])

def start(conn,uid,payload,bank):
    mode=payload.get('mode','numbers')
    if mode not in ('numbers','random','mock','review'): raise ValueError('Неизвестный режим ЕГЭ')
    filter_=payload.get('filter','all')
    if filter_ not in ('all','unseen','mistakes','mastered'): raise ValueError('Неизвестный фильтр')
    numbers=payload.get('numbers',list(RULES))
    if not isinstance(numbers,list) or not numbers or any(type(n) is not int or n not in RULES for n in numbers): raise ValueError('Выберите номера 4–21')
    count=payload.get('count',5)
    if type(count) is not int or count not in (5,10,20,30): raise ValueError('Длина тренировки: 5, 10, 20 или 30')
    timer=payload.get('timer',False)
    if type(timer) is not bool: raise ValueError('Некорректный таймер')
    reveal=payload.get('reveal','immediate')
    if reveal not in ('immediate','end'): raise ValueError('Проверьте режим объяснений')
    by,_=question_stats(conn,uid)
    pool=[q for q in bank.values() if q['number'] in numbers and qualifies(by.get(q['id'],[]),filter_)]
    if mode=='review':
        due={r[0][5:] for r in conn.execute("SELECT question_id FROM learning_progress WHERE user_id=? AND question_id LIKE 'exam:%' AND due_at<=?",(uid,learning.now().isoformat()))}
        pool=[q for q in pool if q['id'] in due]
    if not pool: raise ValueError('Для выбранных условий нет опубликованных заданий')
    if mode=='mock':
        chosen=[]
        for n in RULES:
            options=[q for q in pool if q['number']==n]
            if not options: continue
            chosen.append(random.choice(options))
        reveal='end'; timer=True
        missing=sorted(set(RULES)-{q['number'] for q in chosen})
        label='Тематический вариант №4–21' if not missing else 'Неполный тематический вариант: '+str(len(chosen))+' из 18 номеров'
        seconds=36*60
    else:
        random.shuffle(pool);chosen=pool[:count];seconds=len(chosen)*120
        label={'numbers':'Практика по номерам','random':'Случайная тренировка','review':'Повторение ЕГЭ'}[mode]
    sid=secrets.token_urlsafe(18); stamp=learning.now()
    deadline=(stamp+timedelta(seconds=seconds)).isoformat() if timer else None
    conn.execute('INSERT INTO exam_sessions(id,user_id,mode,questions,created_at,deadline,reveal,label) VALUES(?,?,?,?,?,?,?,?)',
        (sid,uid,mode,json.dumps(chosen,ensure_ascii=False),stamp.isoformat(),deadline,reveal,label))
    return session_view(conn,uid,sid)

def mutate(conn,uid,payload):
    sid=payload.get('session_id');r=row_for(conn,uid,sid)
    if r['finished']: raise ValueError('Тренировка уже завершена')
    if expired(r):
        finish(conn,uid,sid)
        return session_view(conn,uid,sid)
    if type(payload.get('revision')) is not int or payload['revision']!=r['revision']:
        raise ValueError('Состояние изменилось. Восстанови тренировку.')
    action=payload.get('action')
    if action=='finish':
        finish(conn,uid,sid);return session_view(conn,uid,sid)
    qs=json.loads(r['questions']); drafts=json.loads(r['drafts']); results=json.loads(r['results'])
    qid=payload.get('question_id')
    q=next((q for q in qs if q['id']==qid),None)
    if not q: raise ValueError('Задание не входит в тренировку')
    if qid in results and action!='navigate': raise ValueError('Ответ уже принят')
    if action in ('save','answer','navigate'):
        if qid not in results and 'answer' in payload:
            normalize(payload['answer']);drafts[qid]=payload['answer']
        if action=='answer':
            results[qid]=record(conn,uid,sid,q,drafts.get(qid,''))
        position=payload.get('position',r['position'])
        if type(position) is not int or not 0<=position<len(qs): raise ValueError('Некорректная позиция')
        conn.execute('UPDATE exam_sessions SET drafts=?,results=?,position=?,revision=revision+1 WHERE id=?',
            (json.dumps(drafts,ensure_ascii=False),json.dumps(results,ensure_ascii=False),position,sid))
        if action=='answer' and len(results)==len(qs): finish(conn,uid,sid)
        return session_view(conn,uid,sid)
    raise ValueError('Неизвестное действие')

def review_adapters(bank):
    # Generic SRS consumes exactly the same question IDs and central scoring rules.
    return {'exam:'+q['id']:dict(id='exam:'+q['id'],category='exam',topic='ЕГЭ №'+str(q['number'])+' · '+TITLES[q['number']],
        type='exam',prompt=q['prompt'],text=q['text'],options=q['options'],left=q.get('left',[]),
        exam_type=q['type'],answer=q['answer'],alternatives=q['alternatives'],explanation=q['explanation'],
        source=q['source_url'],difficulty=q['difficulty'],format='learn',exam_number=q['number'],exam_data=q) for q in bank.values()}
