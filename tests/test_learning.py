import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import app
import learning as l

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=app.DB
        app.DB=Path(self.tmp.name)/'test.sqlite3'
        self.conn=app.db()
        app.ensure_user(self.conn,42)
        l.sync_legacy(self.conn,42)
        self.q=app.QUESTIONS

    def tearDown(self):
        self.conn.close(); app.DB=self.old_db; self.tmp.cleanup()

    def respond(self,s,correct=True):
        q=self.q[s['question']['id']]
        answer=q['answer'] if correct else (next(i for i,c in enumerate(q['prompt']) if c in app.VOWELS and i!=q['answer']) if q['type']=='stress' else 'ошибка' if q['type']=='text' else next(o for o in q['options'] if o!=q['answer']) if q['type']=='choice' else [999])
        return l.answer(self.conn,42,dict(session_id=s['id'],position=s['position'],answer=answer),self.q)

    def test_all_categories_and_ege_finish(self):
        for mode in ('practice','ege'):
            for category in l.CATEGORIES:
                s=l.start(self.conn,42,dict(mode=mode,category=category),self.q)
                seen=set()
                while not s['finished']:
                    self.assertNotIn(s['question']['id'],seen); seen.add(s['question']['id'])
                    self.assertNotIn('answer',s['question'])
                    r=self.respond(s); self.assertTrue(r['feedback']['correct']); s=r['session']
                self.assertEqual(s['accuracy'],100)

    def test_no_duplicate_xp_or_replayed_answers(self):
        s=l.start(self.conn,42,dict(mode='practice',category='paronyms'),self.q)
        self.respond(s)
        with self.assertRaises(ValueError): self.respond(s)
        qid=s['question']['id']
        self.assertEqual(l.record(self.conn,42,qid,'paronyms',True,'practice'),0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM learning_rewards WHERE user_id=42 AND reward_key LIKE 'answer:%'").fetchone()[0],1)

    def test_daily_identity_and_rotation_and_timeout(self):
        s=l.start(self.conn,42,dict(mode='emergency'),self.q)
        self.assertEqual(s['id'],l.start(self.conn,42,dict(mode='emergency'),self.q)['id'])
        with self.assertRaises(ValueError):
            l.answer(self.conn,42,dict(session_id=s['id'],position=1,timeout=True),self.q)
        instant=l.now()
        with patch.object(l,'now',return_value=instant+timedelta(seconds=11)):
            r=self.respond(s)
            self.assertFalse(r['feedback']['correct']); self.assertTrue(r['feedback']['expired'])
        self.assertTrue(l.start(self.conn,42,dict(mode='emergency'),self.q)['finished'])
        with patch.object(l,'now',return_value=instant+timedelta(days=1)):
            other=l.start(self.conn,42,dict(mode='emergency'),self.q)
            self.assertNotEqual(other['question']['id'],s['question']['id'])

    def test_daily_rewards_once_and_archive(self):
        for mode in ('word','emergency'):
            s=l.start(self.conn,42,dict(mode=mode),self.q)
            r=self.respond(s)
            self.assertTrue(r['session']['finished'])
            with self.assertRaises(ValueError): self.respond(s)
        d=l.dashboard(self.conn,42,self.q)
        self.assertEqual(len(d['archive']),1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM learning_rewards WHERE reward_key LIKE 'emergency:%'").fetchone()[0],1)

    def test_review_intervals_cross_day_and_no_same_day_mastery(self):
        qid='p1'; instant=l.now()
        l.record(self.conn,42,qid,'paronyms',False,'practice')
        with self.assertRaises(ValueError): l.start(self.conn,42,dict(mode='review'),self.q)
        with patch.object(l,'now',return_value=instant+timedelta(days=2)):
            s=l.start(self.conn,42,dict(mode='review'),self.q)
            self.assertEqual(s['question']['id'],qid)
            self.respond(s)
            l.record(self.conn,42,qid,'paronyms',True,'practice')
            self.assertEqual(self.conn.execute('SELECT successes FROM learning_progress WHERE question_id=?',(qid,)).fetchone()[0],1)
        with patch.object(l,'now',return_value=instant+timedelta(days=4)):
            l.record(self.conn,42,qid,'paronyms',True,'practice')
            row=self.conn.execute('SELECT * FROM learning_progress WHERE question_id=?',(qid,)).fetchone()
            self.assertEqual(row['successes'],2)
            self.assertEqual(row['due_at'],(instant+timedelta(days=7)).isoformat())

    def test_survival_lives_and_perfect_record(self):
        s=l.start(self.conn,42,dict(mode='survival'),self.q)
        # Use valid wrong answers for each type, including empty comma sets.
        for _ in range(3):
            q=self.q[s['question']['id']]
            wrong=next((i for i,c in enumerate(q['prompt']) if c in app.VOWELS and i!=q['answer']),None) if q['type']=='stress' else 'ошибка' if q['type']=='text' else next((o for o in q['options'] if o!=q['answer']),None) if q['type']=='choice' else ([] if q['answer'] else [1])
            if wrong is None:
                self.conn.execute('UPDATE learning_sessions SET queue=? WHERE id=?',(json.dumps(['p1']*5),s['id']))
                wrong='одеть'
            r=l.answer(self.conn,42,dict(session_id=s['id'],position=s['position'],answer=wrong),self.q)
            s=r['session']
        self.assertTrue(s['finished']); self.assertEqual(s['lives'],0)
        s=l.start(self.conn,42,dict(mode='survival'),self.q)
        while not s['finished']: s=self.respond(s)['session']
        self.assertEqual(s['best_chain'],5)
        self.assertEqual(l.dashboard(self.conn,42,self.q)['records']['survival'],5)

    def test_timer_levels_resume_and_user_isolation(self):
        for level,seconds in [('beginner',12),('host',8),('pro',5)]:
            s=l.start(self.conn,42,dict(mode='teleprompter',level=level),self.q)
            self.assertEqual(len(json.loads(self.conn.execute('SELECT queue FROM learning_sessions WHERE id=?',(s['id'],)).fetchone()[0])),10)
            self.assertEqual(self.conn.execute('SELECT seconds FROM learning_sessions WHERE id=?',(s['id'],)).fetchone()[0],seconds)
            self.assertEqual(s['deadline'],l.session_view(self.conn,42,s['id'],self.q)['deadline'])
            with self.assertRaises(ValueError): l.session_view(self.conn,43,s['id'],self.q)
        self.conn.commit()
        with app.db() as other:
            self.assertEqual(l.session_view(other,42,s['id'],self.q)['id'],s['id'])

    def test_import_validation_and_normalization(self):
        rows=json.loads(Path('data/questions.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(l.validate_questions(rows)),52)
        with self.assertRaises(ValueError): l.validate_questions(rows+[rows[0]])
        self.assertTrue(l.check(self.q['s1'],'  ТУФЕЛЬ  '))
        self.assertFalse(l.check(self.q['s1'],'туфлей'))
        self.assertNotEqual(l.normalize('ёлка'),l.normalize('елка'))
        with self.assertRaises(ValueError): l.check(self.q['c1'],[True])
        with self.assertRaises(ValueError): l.check(self.q['eo1'],[1,1])

    def test_rank_goal_and_achievements(self):
        self.assertEqual(l.rank(99)['level'],1); self.assertEqual(l.rank(100)['level'],2)
        for i in range(1,11): l.record(self.conn,42,'p'+str(i),'paronyms',True,'practice')
        earned=l.unlock(self.conn,42)
        self.assertTrue({'first','ten','paronyms'}<={a['id'] for a in earned})
        self.assertEqual(l.unlock(self.conn,42),[])
        self.assertEqual(l.record(self.conn,42,'p1','paronyms',True,'practice'),0)
        self.assertEqual(self.conn.execute("SELECT xp FROM learning_rewards WHERE reward_key LIKE 'goal:%'").fetchone()[0],30)

    def test_exam_config_and_additive_migration(self):
        l.migrate(self.conn); l.migrate(self.conn)
        self.assertIsNotNone(self.conn.execute('SELECT id FROM users WHERE id=42').fetchone())
        with patch.dict('os.environ',{'EGE_DATE':'2000-01-01','EGE_DATE_OFFICIAL':'0'}):
            d=l.dashboard(self.conn,42,self.q); self.assertLess(d['exam']['days'],0); self.assertFalse(d['exam']['official'])
        with patch.dict('os.environ',{'EGE_DATE':'bad'}): self.assertIn('error',l.dashboard(self.conn,42,self.q)['exam'])

    def test_legacy_migration_once(self):
        app.ensure_user(self.conn,99)
        self.conn.execute("INSERT INTO answers(user_id,word_id,correct,answered_at,mode) VALUES(99,'old',1,'2026-11-01T00:00:00+00:00','round')")
        l.sync_legacy(self.conn,99); l.sync_legacy(self.conn,99)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM learning_answers WHERE user_id=99').fetchone()[0],1)
        self.assertEqual(l.dashboard(self.conn,99,self.q)['xp'],0)

    def test_teleprompter_review_keeps_all_errors_and_timeouts_after_reopen(self):
        s=l.start(self.conn,42,dict(mode='teleprompter'),self.q)
        stress=next(q for q in self.q.values() if q['type']=='stress')
        queue=['p1','s1','c1','o1',stress['id']]
        self.conn.execute('UPDATE learning_sessions SET queue=? WHERE id=?',(json.dumps(queue),s['id']))
        for position,value in enumerate(['одеть','туфлей',[],'е'],1):
            r=l.answer(self.conn,42,dict(session_id=s['id'],position=position,answer=value),self.q)
            self.assertNotIn('mistakes',r['session'])
            self.assertTrue(all('review' not in outcome for outcome in r['session']['outcomes']))
        stamp=l.now()
        with patch.object(l,'now',return_value=stamp+timedelta(seconds=13)):
            r=l.answer(self.conn,42,dict(session_id=s['id'],position=5,answer=None,timeout=True),self.q)
        self.assertTrue(r['session']['finished'])
        errors=r['session']['mistakes']
        self.assertEqual([e['position'] for e in errors],[1,2,3,5])
        self.assertEqual([e['chosen'] for e in errors],['одеть','туфлей',[],None])
        self.assertTrue(errors[-1]['expired'])
        self.assertFalse(errors[0]['expired'])
        self.assertEqual(errors[0]['answer'],'надеть')
        self.assertEqual(errors[2]['answer'],[3])
        self.assertTrue(all(e['explanation'] and e['source'] for e in errors))
        self.conn.commit()
        with app.db() as other:
            restored=l.session_view(other,42,s['id'],self.q)
            self.assertEqual(restored['mistakes'],errors)
        # Older saved sessions contain correctness but no chosen-answer snapshot.
        old_outcomes=json.loads(self.conn.execute('SELECT outcomes FROM learning_sessions WHERE id=?',(s['id'],)).fetchone()[0])
        for outcome in old_outcomes: outcome.pop('review',None)
        self.conn.execute('UPDATE learning_sessions SET outcomes=? WHERE id=?',(json.dumps(old_outcomes),s['id']))
        legacy=l.session_view(self.conn,42,s['id'],self.q)['mistakes']
        self.assertEqual(len(legacy),4)
        self.assertNotIn('chosen',legacy[0])
        self.assertNotIn('expired',legacy[0])
        self.assertEqual(legacy[0]['answer'],'надеть')

    def test_teleprompter_perfect_has_empty_review(self):
        s=l.start(self.conn,42,dict(mode='teleprompter'),self.q)
        while not s['finished']: s=self.respond(s)['session']
        self.assertEqual(s['mistakes'],[])

if __name__=='__main__': unittest.main()
