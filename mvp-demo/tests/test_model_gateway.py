import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from budget_store import BudgetStore,BudgetPaused,MODEL,VERSION
from model_gateway import DeepSeekGateway,ModelError,load_config,ENDPOINT,http_transport
from platform_ports import LOCAL_ACTOR

PRICE={'model':MODEL,'version':VERSION,'currency':'CNY','unit':'per_million_tokens','input':'2','output':'3','reference':'SYNTHETIC TEST ONLY'}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=BudgetStore(Path(self.tmp.name))
        self.info=self.store.create(LOCAL_ACTOR,'a'*64,'b'*64,PRICE,max_input=32000,max_output=1000)
        self.bid=self.info['budget_id'];self.binding=self.info['binding']
        self.config={'endpoint':ENDPOINT,'price':PRICE,'secret':'TEST-NOT-A-REAL-KEY','valid_until':time.time()+100}
        self.transport=Mock(return_value={'model':MODEL,'choices':[{'finish_reason':'stop','message':{'content':'{"requests":[]}'}}],
                                          'usage':{'prompt_tokens':100,'completion_tokens':20}})
        self.gateway=DeepSeekGateway(self.store,self.config,self.transport)
        self.messages=[{'role':'system','content':'Return JSON only.'},{'role':'user','content':'Untrusted example data.'}]

    def allow(self):
        q=self.store.quote(LOCAL_ACTOR,self.bid,'0.067')
        self.store.authorize(LOCAL_ACTOR,self.bid,q['quote_id'],'grant-0001',True)

    def call(self,key='request-0001'):
        return self.gateway.execute(LOCAL_ACTOR,self.bid,self.binding,key,self.messages)

    def test_missing_configuration_and_no_authorization_never_calls(self):
        with self.assertRaises(ModelError):load_config({})
        with self.assertRaises(BudgetPaused):self.call()
        self.transport.assert_not_called()

    def test_fixed_model_controlled_output_cache_and_usage(self):
        self.allow();result=self.call();self.assertEqual(result,self.call());self.transport.assert_called_once()
        body=json.loads(self.transport.call_args.args[1]);self.assertEqual(body['model'],MODEL)
        self.assertEqual(body['max_tokens'],1000);self.assertFalse(body['stream'])
        self.assertTrue(result['usable']);self.assertEqual(self.store.view(LOCAL_ACTOR,self.bid)['spent'],260)
        self.assertFalse(result['actual_version_verified'])

    def test_timeout_holds_amount_and_same_key_does_not_retry(self):
        self.allow();self.transport.side_effect=TimeoutError('TEST-NOT-A-REAL-KEY')
        with self.assertRaises(ModelError) as caught:self.call()
        self.assertNotIn('TEST-NOT-A-REAL-KEY',str(caught.exception))
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.bid)['held'],67000)
        with self.assertRaises(BudgetPaused):self.call()
        self.transport.assert_called_once()

    def test_truncated_or_invalid_json_still_records_known_cost(self):
        self.allow();self.transport.return_value['choices'][0]['finish_reason']='length'
        result=self.call();self.assertFalse(result['usable']);self.assertIsNone(result['content'])
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.bid)['spent'],260)

    def test_missing_usage_stays_uncertain(self):
        self.allow();self.transport.return_value.pop('usage')
        with self.assertRaises(ModelError):self.call()
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.bid)['held'],67000)

    def test_changed_price_destination_expiry_and_large_input_denied(self):
        self.allow()
        for changes in [{'endpoint':'https://example.org'},{'price':dict(PRICE,input='4')},{'valid_until':0}]:
            self.gateway.config={**self.config,**changes}
            with self.assertRaises((ModelError,BudgetPaused)):self.call()
        self.gateway.config=self.config;self.messages[1]['content']='x'*24000
        with self.assertRaises(ModelError):self.call()
        self.transport.assert_not_called()

    def test_http_429_retries_once_only_after_rejection(self):
        class Response:
            def __init__(self,status):self.status=status;self.once=False
            def getheader(self,*_):return 'application/json'
            def read1(self,*_):
                if self.once:return b''
                self.once=True
                return b'{"ok":true}'
        statuses=iter([429,200])
        class Connection:
            sock=None
            def __init__(self,*_,**__):self.response=Response(next(statuses))
            def request(self,*_,**__):pass
            def getresponse(self):return self.response
            def close(self):pass
        with patch('model_gateway.http.client.HTTPSConnection',Connection), patch('model_gateway.time.sleep') as pause:
            self.assertEqual(http_transport('TEST-KEY',b'{}'),{'ok':True})
            pause.assert_called_once()

    def test_http_500_and_business_error_never_disclose_key(self):
        class Rejected:
            status=500
            def getheader(self,*_):return 'application/json'
        class Connection:
            def __init__(self,*_,**__):pass
            def request(self,*_,**__):pass
            def getresponse(self):return Rejected()
            def close(self):pass
        with patch('model_gateway.http.client.HTTPSConnection',Connection):
            with self.assertRaises(ModelError) as error:http_transport('TEST-NOT-A-REAL-KEY',b'{}')
        self.assertNotIn('TEST-NOT-A-REAL-KEY',str(error.exception))
        self.allow();self.transport.return_value={'error':{'message':'TEST-NOT-A-REAL-KEY'}}
        with self.assertRaises(ModelError) as error:self.call()
        self.assertNotIn('TEST-NOT-A-REAL-KEY',str(error.exception))
        self.assertGreater(self.store.view(LOCAL_ACTOR,self.bid)['held'],0)


if __name__=='__main__':unittest.main()
