import copy
import csv
import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import app
import exam
import learning
import import_exam

class ExamTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.previous=app.DB
        app.DB=Path(self.tmp.name)/'exam.sqlite3';self.conn=app.db()
        app.ensure_user(self.conn,7);learning.sync_legacy(self.conn,7)
        self.bank=app.EXAM_BANK

    def tearDown(self):
        self.conn.close();app.DB=self.previous;self.tmp.cleanup()

    def act(self,s,action='answer',answer=None,position=None,qid=None):
        q=s['questions'][s['position']]
        payload=dict(session_id=s['id'],revision=s['revision'],action=action,question_id=qid or q['id'],position=s['position'] if position is None else position)
        if answer is not None:payload['answer']=answer
        return exam.mutate(self.conn,7,payload)

    def test_allowed_numbers_launch_and_grade(self):
        self.assertEqual({q['number'] for q in self.bank.values()},set(range(4,22)))
        self.assertTrue(all(not q['text'] and not q.get('text_id') for q in self.bank.values()))
        self.assertEqual(len(self.bank),109)
        for number in range(4,22):
            s=exam.start(self.conn,7,dict(mode='numbers',numbers=[number],count=5),self.bank)
            self.assertEqual(len({q['id'] for q in s['questions']}),s['total'])
            while not s['finished']:
                q=next(q for q in s['questions'] if q['id'] not in s['answered'])
                self.assertNotIn('answer',q);self.assertNotIn('explanation',q)
                s=self.act(s,answer=self.bank[q['id']]['answer'],qid=q['id'])
            self.assertEqual(s['correct'],s['total']);self.assertEqual(s['points'],s['max_points'])

    def test_scoring_order_duplicates_partial_and_strict_text(self):
        q=self.bank['syntax-1']
        for value,expected in [('12345',2),('21345',1),('12346',1),('02345',1),('123',1),('98765',0),('123456',0),('',0),('1234x',0)]:
            self.assertEqual(exam.score(q,value),expected,(value,expected))
        q=next(q for q in self.bank.values() if q['number']==4)
        self.assertEqual(exam.score(q,q['answer'][::-1]),1)
        self.assertEqual(exam.score(q,q['answer']+q['answer'][0]),0)
        self.assertEqual(exam.score(q,','.join(q['answer'])),0)
        self.assertEqual(exam.score(self.bank['morph-1'],'  ТУФЕЛЬ  '),1)
        self.assertEqual(exam.score(self.bank['morph-1'],'туфлей'),0)
        self.assertEqual(exam.score(self.bank['par-1'],'эффектив ный'),0)
        self.assertNotEqual(exam.normalize('ё'),exam.normalize('е'))

    def test_text_tasks_are_rejected(self):
        q=copy.deepcopy(self.bank['new-4-1'])
        q['number']=22
        with self.assertRaises(ValueError):exam.validate_bank([q])
        q=copy.deepcopy(self.bank['new-4-1'])
        q['text']='Общий исходный текст'
        with self.assertRaises(ValueError):exam.validate_bank([q])

    def test_spelling_keys_after_linguistic_review(self):
        keys={'orth-9-1':'245','orth-9-2':'134','orth-9-3':'235',
              'orth-10-1':'135','orth-10-2':'124','orth-10-3':'123',
              'orth-11-1':'12345','orth-11-2':'125','orth-11-3':'34',
              'orth-12-1':'23','orth-12-2':'134','orth-12-3':'134'}
        for qid,key in keys.items():self.assertEqual(self.bank[qid]['answer'],key)

    def test_mock_drafts_resume_no_early_answers(self):
        s=exam.start(self.conn,7,dict(mode='mock'),self.bank)
        self.assertEqual([q['number'] for q in s['questions']],list(range(4,22)))
        self.assertEqual(s['max_points'],19);self.assertEqual(s['reveal'],'end')
        q=s['questions'][0];correct=self.bank[q['id']]['answer']
        s=self.act(s,'save',correct)
        s=self.act(s,'navigate',correct,position=3)
        self.conn.commit()
        with app.db() as other:
            restored=exam.session_view(other,7,s['id'])
        self.assertEqual(restored['position'],3);self.assertEqual(restored['questions'][0]['draft'],correct)
        self.assertTrue(all(q['result'] is None for q in restored['questions']))
        self.assertIsNone(restored['points'])
        final=self.act(s,'finish')
        self.assertTrue(final['finished']);self.assertEqual(final['questions'][0]['result']['score'],1)
        self.assertEqual(final['questions'][1]['result']['chosen'],'')

    def test_deferred_results_no_xp_duplicates_and_ownership(self):
        s=exam.start(self.conn,7,dict(mode='random',count=5,reveal='end'),self.bank)
        old=copy.deepcopy(s);q=s['questions'][0]
        s=self.act(s,answer=self.bank[q['id']]['answer'])
        self.assertIsNone(s['questions'][0]['result']);self.assertIsNone(s['correct'])
        with self.assertRaises(ValueError):self.act(old,answer=self.bank[q['id']]['answer'])
        with self.assertRaises(ValueError):exam.session_view(self.conn,8,s['id'])
        final=self.act(s,'finish')
        reward_count=self.conn.execute('SELECT COUNT(*) FROM learning_rewards').fetchone()[0]
        self.assertTrue(exam.session_view(self.conn,7,s['id'])['finished'])
        self.assertEqual(reward_count,self.conn.execute('SELECT COUNT(*) FROM learning_rewards').fetchone()[0])
        with self.assertRaises(ValueError):self.act(final,'finish')

    def test_expiry_grades_saved_drafts_only(self):
        s=exam.start(self.conn,7,dict(mode='random',count=5,timer=True),self.bank)
        q=s['questions'][0];s=self.act(s,'save',self.bank[q['id']]['answer'])
        stamp=learning.now()
        with patch.object(learning,'now',return_value=stamp+timedelta(hours=1)):
            final=exam.session_view(self.conn,7,s['id'])
            self.assertTrue(final['finished']);self.assertEqual(final['questions'][0]['result']['correct'],True)
            self.assertEqual(len(final['answered']),5)

    def test_srs_shared_xp_and_exam_statistics(self):
        s=exam.start(self.conn,7,dict(mode='numbers',numbers=[5]),self.bank)
        q=s['questions'][0];s=self.act(s,answer='ошибка')
        qid='exam:'+q['id']
        self.conn.execute('UPDATE learning_progress SET due_at=? WHERE user_id=7 AND question_id=?',((learning.now()-timedelta(days=1)).isoformat(),qid))
        review=learning.start(self.conn,7,dict(mode='review'),app.QUESTIONS)
        self.assertEqual(review['question']['type'],'exam');self.assertNotIn('exam_data',review['question'])
        result=learning.answer(self.conn,7,dict(session_id=review['id'],position=1,answer=self.bank[q['id']]['answer']),app.QUESTIONS)
        self.assertTrue(result['feedback']['correct'])
        self.assertEqual(exam.dashboard(self.conn,7,self.bank)['mistakes'],0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM exam_attempts WHERE question_id=?',(q['id'],)).fetchone()[0],2)
        self.assertEqual(learning.record(self.conn,7,qid,'exam',True,'exam'),0)

    def test_filters_mastery_requires_different_days(self):
        s=exam.start(self.conn,7,dict(mode='numbers',numbers=[5]),self.bank)
        q=s['questions'][0];self.act(s,answer=self.bank[q['id']]['answer'])
        self.assertFalse(exam.qualifies(exam.question_stats(self.conn,7)[0][q['id']],'mastered'))
        self.assertFalse(exam.qualifies(exam.question_stats(self.conn,7)[0][q['id']],'unseen'))
        self.assertEqual(exam.dashboard(self.conn,7,self.bank)['numbers'][1]['solved'],1)
        for days in (1,2):
            with patch.object(learning,'now',return_value=learning.now()+timedelta(days=days)):
                exam.record(self.conn,7,'separate-'+str(days),self.bank[q['id']],self.bank[q['id']]['answer'])
        self.assertTrue(exam.qualifies(exam.question_stats(self.conn,7)[0][q['id']],'mastered'))

    def test_import_json_csv_rights_errors_and_atomicity(self):
        rows=list(self.bank.values());destination=Path(self.tmp.name)/'bank.json';source=Path(self.tmp.name)/'input.json'
        source.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
        report=import_exam.import_bank(source,destination)
        self.assertTrue(report['written']);self.assertEqual(report['published'],len(rows))
        original=destination.read_bytes()
        bad=copy.deepcopy(rows);bad[0]['rights']=dict(status='unknown')
        source.write_text(json.dumps(bad),encoding='utf-8')
        with self.assertRaises(ValueError):import_exam.import_bank(source,destination)
        self.assertEqual(destination.read_bytes(),original)
        with self.assertRaises(ValueError):exam.validate_bank(rows+[rows[0]])
        csvpath=Path(self.tmp.name)/'sample.csv'
        fields=list({k for q in rows for k in q})
        with csvpath.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
            for q in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if k in import_exam.JSON_FIELDS else v for k,v in q.items()})
        checked=import_exam.import_bank(csvpath,destination,check=True)
        self.assertEqual(checked['count'],len(rows));self.assertFalse(checked['written'])

    def test_partial_mock_is_labeled_and_migrations_preserve_progress(self):
        bank={k:q for k,q in self.bank.items() if q['number'] in (4,5)}
        s=exam.start(self.conn,7,dict(mode='mock'),bank)
        self.assertIn('Неполный',s['label']);self.assertEqual(s['total'],2)
        exam.migrate(self.conn);exam.migrate(self.conn)
        self.assertIsNotNone(self.conn.execute('SELECT * FROM users WHERE id=7').fetchone())

if __name__=='__main__':unittest.main()
