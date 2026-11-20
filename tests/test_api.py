import concurrent.futures
import json
import tempfile
import io
import unittest
import urllib.request
import urllib.error
from pathlib import Path

import app

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db,self.old_dev=app.DB,app.DEV
        app.DB=Path(self.tmp.name)/'api.sqlite3';app.DEV=True

    def tearDown(self):
        app.DB,app.DEV=self.old_db,self.old_dev;self.tmp.cleanup()

    def request(self,path,data=None,auth='dev'):
        # Exercise the real handlers in memory: this managed environment denies
        # outgoing sockets even to loopback. Database concurrency remains real.
        handler=object.__new__(app.Handler)
        raw=json.dumps(data).encode() if data is not None else b''
        handler.path=path
        handler.command='POST' if data is not None else 'GET'
        handler.headers={'X-Telegram-Init-Data':auth,'Content-Length':str(len(raw))}
        handler.rfile=io.BytesIO(raw);handler.wfile=io.BytesIO()
        status=[]
        handler.send_response=lambda code,*args:status.append(code)
        handler.send_header=lambda *args:None
        handler.end_headers=lambda:None
        handler.send_error=lambda code,*args:status.append(code)
        if data is not None:handler.do_POST()
        else:handler.do_GET()
        return status[0],handler.wfile.getvalue()

    def test_assets_auth_and_bad_payload(self):
        for asset in ('/','/app.js','/studio.js','/style.css','/studio.css','/word.css','/exam.js','/exam.css'):
            status,body=self.request(asset);self.assertEqual(status,200);self.assertTrue(body)
        self.assertEqual(self.request('/api/home',auth='')[0],400)
        self.assertEqual(self.request('/api/learning/start',[])[0],400)
        status,body=self.request('/api/home');self.assertEqual(status,200);self.assertIn('learning',json.loads(body))
        self.assertEqual(self.request('/data/questions.json')[0],404)

    def test_concurrent_daily_and_answer_replay(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.request('/api/learning/start',dict(mode='word')),range(2)))
        self.assertTrue(all(r[0]==200 for r in results))
        sessions=[json.loads(r[1]) for r in results]
        self.assertEqual(sessions[0]['id'],sessions[1]['id'])
        s=sessions[0];self.assertNotIn('source',s['question']);self.assertNotIn('answer',s['question'])
        payload=dict(session_id=s['id'],position=1,answer=app.QUESTIONS[s['question']['id']]['answer'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.request('/api/learning/answer',payload),range(2)))
        self.assertEqual(sorted(r[0] for r in results),[200,400])
        home=json.loads(self.request('/api/home')[1])
        self.assertEqual(home['learning']['today']['total'],1)
        with app.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM learning_rewards WHERE reward_key LIKE 'answer:%'").fetchone()[0],1)

    def test_exam_api_drafts_and_hidden_answers(self):
        status,body=self.request('/api/exam/home')
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['numbers']),18)
        status,body=self.request('/api/exam/start',dict(mode='mock'))
        self.assertEqual(status,200);s=json.loads(body);q=s['questions'][0]
        self.assertIsNone(q['result']);self.assertNotIn('answer',q)
        status,body=self.request('/api/exam/action',dict(session_id=s['id'],revision=s['revision'],action='save',question_id=q['id'],answer=app.EXAM_BANK[q['id']]['answer']))
        self.assertEqual(status,200);s=json.loads(body)
        status,body=self.request('/api/exam/action',dict(session_id=s['id'],revision=s['revision'],action='finish'))
        self.assertEqual(status,200);self.assertTrue(json.loads(body)['finished'])
        self.assertEqual(self.request('/data/exam_questions.json')[0],404)

if __name__=='__main__':unittest.main()
