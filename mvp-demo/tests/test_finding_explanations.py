import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from budget_store import MODEL, VERSION
from finding_explanations import FindingExplanationService, minimal_evidence, DISCLAIMER
from model_gateway import ENDPOINT, ModelError, load_config
from platform_ports import LOCAL_ACTOR
from review_store import ReviewStore

PRICE={'model':MODEL,'version':VERSION,'currency':'USD','unit':'per_million_tokens',
       'input':'0.30','output':'1.20','reference':'SYNTHETIC TEST ONLY'}
VALID={'what':'两列存在稳定差值。','why':'35 行都符合相同关系，建议核对生成过程。',
       'benign_explanations':['其中一列可能由另一列加常数计算。'],
       'check_steps':['查看原始记录与计算公式。'],'report_summary':'发现待核对的固定平移信号。'}


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.scan='abcdef123456'; self.finding='FD-0001'
        self.item={'id':self.finding,'title_cn':'固定平移','file':'sample.csv','sheet':'Sheet1',
                   'location':'第 2–36 行','columns':['control','treated'],'n':35,
                   'summary_cn':'35 行差值均为 0.3','rule':'treated = control + 0.3',
                   'raw':{'offset':0.3,'whole_file':'DO-NOT-SEND'},
                   'evidence':{'headers':['control','treated'],
                               'rows':[{'row_idx':i,'values':[i,i+.3]} for i in range(2,40)]}}
        self.result={'scan_id':self.scan,'findings':[self.item],'source':'sample.csv'}
        ReviewStore(self.root).register(LOCAL_ACTOR,self.result)
        self.config={'endpoint':ENDPOINT,'price':PRICE,'secret':'TEST-NOT-A-REAL-KEY',
                     'valid_until':time.time()+3600}
        self.transport=Mock(side_effect=self.answer)
        self.service=FindingExplanationService(self.root,lambda:self.config,self.transport)

    def answer(self, secret, body):
        content=json.loads(body)['messages'][1]['content']
        self.assertNotIn('DO-NOT-SEND',content)
        self.assertNotIn('row_idx": 39',content)
        self.assertLess(len(content.encode()),3001)
        return {'model':MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(VALID)}}],
                'usage':{'prompt_tokens':400,'completion_tokens':80}}

    def test_minimal_evidence_and_schema(self):
        evidence=minimal_evidence(self.item)
        self.assertEqual(len(evidence['samples']),3)
        self.assertNotIn('whole_file',json.dumps(evidence))
        self.assertLessEqual(len(json.dumps(evidence).encode()),3000)
        from finding_explanations import validate_explanation
        with self.assertRaises(ModelError):
            validate_explanation({**VALID,'report_summary':'这证明作者造假。'})

    def test_quote_confirm_persists_and_does_not_change_scan(self):
        quote=self.service.quote(LOCAL_ACTOR,self.scan,self.finding)
        self.assertEqual(quote['status'],'awaiting_confirmation')
        self.transport.assert_not_called()
        result=self.service.run(LOCAL_ACTOR,self.scan,self.finding,quote['quote']['quote_id'],'confirm-0001',True)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['explanation']['disclaimer'],DISCLAIMER)
        self.assertEqual(self.service.view(LOCAL_ACTOR,self.scan,self.finding),result)
        self.assertEqual(ReviewStore(self.root).view(LOCAL_ACTOR,self.scan)['revision'],0)
        self.assertEqual(self.service.run(LOCAL_ACTOR,self.scan,self.finding,'ignored','ignored',False),result)
        self.transport.assert_called_once()
        self.assertNotIn('TEST-NOT-A-REAL-KEY',json.dumps(result))

    def test_timeout_and_malformed_answer_leave_scan_readable(self):
        for failure in ('timeout','malformed'):
            with self.subTest(failure=failure):
                tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
                root=Path(tmp.name); ReviewStore(root).register(LOCAL_ACTOR,self.result)
                transport=Mock(side_effect=TimeoutError('TEST-NOT-A-REAL-KEY')) if failure=='timeout' else Mock(
                    return_value={'model':MODEL,'choices':[{'finish_reason':'stop','message':{'content':'{}'}}],
                                  'usage':{'prompt_tokens':400,'completion_tokens':80}})
                service=FindingExplanationService(root,lambda:self.config,transport)
                quote=service.quote(LOCAL_ACTOR,self.scan,self.finding)
                result=service.run(LOCAL_ACTOR,self.scan,self.finding,quote['quote']['quote_id'],'confirm-0001',True)
                self.assertEqual(result['status'],'failed')
                self.assertIsNone(result['explanation'])
                self.assertNotIn('TEST-NOT-A-REAL-KEY',json.dumps(result))
                self.assertEqual(ReviewStore(root).view(LOCAL_ACTOR,self.scan)['revision'],0)
                transport.assert_called_once()

    def test_environment_overrides_are_strict(self):
        configured=load_config({'DEEPSEEK_API_KEY':'TEST-PLACEHOLDER',
                                'DEEPSEEK_BASE_URL':ENDPOINT,'DEEPSEEK_MODEL':MODEL,
                                'LOCALAPPDATA':str(self.root/'no-config-here')})
        self.assertEqual(configured['model'],MODEL)
        self.assertEqual(configured['secret'],'TEST-PLACEHOLDER')
        with self.assertRaises(ModelError):
            load_config({'DEEPSEEK_BASE_URL':'https://example.org','DEEPSEEK_MODEL':MODEL})
        with self.assertRaises(ModelError):
            load_config({'DEEPSEEK_BASE_URL':ENDPOINT,'DEEPSEEK_MODEL':'invented-model'})

    def test_http_quote_explain_and_frontend(self):
        folder=self.root/self.scan; folder.mkdir()
        (folder/'result.json').write_text(json.dumps(self.result),encoding='utf-8')
        (folder/'report.html').write_text('report',encoding='utf-8')
        with patch.object(app,'RUNTIME_DIR',self.root), patch.object(app.finding_explanations,'FindingExplanationService',lambda root:self.service):
            server=ThreadingHTTPServer(('127.0.0.1',0),app.DemoHandler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=5)))
            def request(path,body=None):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=15)
                try:
                    connection.request('POST' if body is not None else 'GET',path,
                                       json.dumps(body) if body is not None else None,
                                       {'Content-Type':'application/json'})
                    response=connection.getresponse(); data=response.read()
                    return response.status, json.loads(data) if 'application/json' in response.getheader('Content-Type','') else data
                finally:connection.close()
            self.assertEqual(request('/')[0],200)
            self.assertIn(b'finding-ai.js',request('/')[1])
            self.assertEqual(request('/finding-ai.js')[0],200)
            self.assertEqual(request('/api/health')[0],200)
            self.assertEqual(request(f'/api/explanations/{self.scan}/{self.finding}')[1]['ai']['status'],'not_started')
            quote=request('/api/explanations/quote',{'scan_id':self.scan,'finding_id':self.finding})[1]['ai']
            self.assertEqual(quote['status'],'awaiting_confirmation')
            result=request('/api/explanations/run',{'scan_id':self.scan,'finding_id':self.finding,
                'quote_id':quote['quote']['quote_id'],'request_key':'confirm-0001','confirmed':True})[1]['ai']
            self.assertEqual(result['status'],'completed')
            self.assertEqual(request(f'/api/explanations/{self.scan}/{self.finding}')[1]['ai']['status'],'completed')
            self.assertEqual(request(f'/api/explanations/{self.scan}/FD-9999')[0],400)


if __name__=='__main__':unittest.main()
