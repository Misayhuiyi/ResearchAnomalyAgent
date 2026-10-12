import sys
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from platform_ports import LOCAL_ACTOR, Actor
from budget_store import BudgetStore, BudgetError, BudgetPaused, MODEL, VERSION, cost

# Synthetic unit prices, never provider pricing or authorization to make paid requests.
PRICE={'model':MODEL,'version':VERSION,'currency':'CNY','unit':'per_million_tokens',
       'input':'2','output':'3','reference':'SYNTHETIC TEST ONLY'}


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.time=1000
        self.store=BudgetStore(Path(self.tmp.name),lambda:self.time)
        self.info=self.store.create(LOCAL_ACTOR,'a'*64,'b'*64,PRICE,max_calls=3,max_input=100,max_output=100,max_seconds=60)
        self.id=self.info['budget_id']; self.binding=self.info['binding']

    def allow(self,amount='0.0005',key='grant-0001'):
        q=self.store.quote(LOCAL_ACTOR,self.id,amount)
        return q,self.store.authorize(LOCAL_ACTOR,self.id,q['quote_id'],key,True)

    def reserve(self,key='request-0001',**changes):
        args=dict(actor=LOCAL_ACTOR,budget=self.id,binding=self.binding,key=key,request_hash='c'*64,input_max=100,output_max=100)
        args.update(changes);return self.store.reserve(**args)

    def test_unconfigured_or_wrong_model_and_no_authorization(self):
        for price in [{},dict(PRICE,model='other'),dict(PRICE,reference=''),dict(PRICE,input='NaN')]:
            with self.assertRaises(BudgetError):self.store.create(LOCAL_ACTOR,'a'*64,'b'*64,price)
        with self.assertRaises(BudgetPaused):self.reserve()
        q=self.store.quote(LOCAL_ACTOR,self.id,'0.0005')
        with self.assertRaises(BudgetError):self.store.authorize(LOCAL_ACTOR,self.id,q['quote_id'],'grant-0001',False)
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.id)['cap_micros'],0)

    def test_grant_replay_exact_cap_and_addition_keeps_usage(self):
        q,cap=self.allow();self.assertEqual(cap,500)
        self.assertEqual(self.store.authorize(LOCAL_ACTOR,self.id,q['quote_id'],'grant-0001',True),500)
        self.reserve();self.assertTrue(self.store.claim(LOCAL_ACTOR,self.id,'request-0001'))
        self.store.settle(LOCAL_ACTOR,self.id,'request-0001',20,20,{'summary':'已核对'})
        with self.assertRaises(BudgetPaused):self.reserve('request-0002')
        quote,_=self.allow('0.001','grant-0002')
        self.assertEqual(quote['spent_micros'],100);self.assertEqual(quote['additional_micros'],500)
        self.reserve('request-0002')
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.id)['spent'],100)

    def test_concurrent_reserve_and_claim_only_once(self):
        self.allow()
        def attempt(i):
            try:return self.reserve(f'request-{i:04}')['new']
            except BudgetPaused:return False
        with ThreadPoolExecutor(2) as pool: answers=list(pool.map(attempt,[1,2]))
        self.assertEqual(sum(answers),1)
        key='request-0001' if answers[0] else 'request-0002'
        with ThreadPoolExecutor(2) as pool: claimed=list(pool.map(lambda _:self.store.claim(LOCAL_ACTOR,self.id,key),[1,2]))
        self.assertEqual(sum(claimed),1)

    def test_timeout_restart_keeps_reservation_and_never_resends(self):
        self.allow();self.reserve();self.store.claim(LOCAL_ACTOR,self.id,'request-0001')
        self.store=BudgetStore(Path(self.tmp.name),lambda:self.time)
        self.store.recover(LOCAL_ACTOR,self.id)
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.id)['held'],500)
        self.assertEqual(self.reserve()['state'],'uncertain')
        self.assertFalse(self.store.claim(LOCAL_ACTOR,self.id,'request-0001'))
        with self.assertRaises(BudgetPaused):self.reserve('request-0002')

    def test_idempotency_owner_binding_and_token_limits(self):
        self.allow();self.assertTrue(self.reserve()['new']);self.assertFalse(self.reserve()['new'])
        for changes in [{'request_hash':'d'*64},{'actor':Actor('x','x')},{'binding':'d'*64}]:
            with self.assertRaises(BudgetError):self.reserve(**changes)
        with self.assertRaises(BudgetError):self.reserve('request-0002',input_max=101)
        with self.assertRaises(BudgetError):self.reserve('request-0002',input_max=True)

    def test_cancel_releases_only_unsent(self):
        self.allow('0.002');self.reserve();self.store.claim(LOCAL_ACTOR,self.id,'request-0001');self.reserve('request-0002')
        self.store.cancel(LOCAL_ACTOR,self.id)
        view=self.store.view(LOCAL_ACTOR,self.id)
        self.assertTrue(view['stopped']);self.assertEqual(view['held'],500)
        with self.assertRaises(BudgetPaused):self.store.claim(LOCAL_ACTOR,self.id,'request-0002')
        with self.assertRaises(BudgetPaused):self.reserve('request-0003')

    def test_deadline_count_and_expiry(self):
        self.allow('0.002');self.reserve();self.time+=61
        with self.assertRaises(BudgetPaused):self.store.claim(LOCAL_ACTOR,self.id,'request-0001')
        with self.assertRaises(BudgetPaused):self.reserve('request-0002')
        self.time=1000
        for key in ['request-0002','request-0003']:self.reserve(key)
        with self.assertRaises(BudgetPaused):self.reserve('request-0004')
        self.time+=86401
        with self.assertRaises(BudgetPaused):self.store.quote(LOCAL_ACTOR,self.id,'1')

    def test_unknown_cost_retained_known_overrun_stops_and_records(self):
        self.allow();self.reserve();self.store.claim(LOCAL_ACTOR,self.id,'request-0001')
        self.assertEqual(self.store.settle(LOCAL_ACTOR,self.id,'request-0001')['state'],'uncertain')
        self.assertEqual(self.store.view(LOCAL_ACTOR,self.id)['held'],500)
        self.assertTrue(self.store.settle(LOCAL_ACTOR,self.id,'request-0001',200,200)['overrun'])
        view=self.store.view(LOCAL_ACTOR,self.id)
        self.assertEqual(view['spent'],1000);self.assertTrue(view['stopped'])
        with self.assertRaises(BudgetError):self.store.settle(LOCAL_ACTOR,self.id,'request-0001',1,1)

    def test_micro_rounding_never_under_reserves(self):
        self.assertEqual(cost(dict(PRICE,input='0.1',output='0.1'),1,1),1)

    def test_operator_receipt_reconciles_once_without_retry_or_result(self):
        self.allow();self.reserve();self.store.claim(LOCAL_ACTOR,self.id,'request-0001')
        with self.assertRaises(BudgetError):
            self.store.reconcile(LOCAL_ACTOR,self.id,'request-0001',200,'CNY','c'*64,'Operator','provider-1')
        self.store.recover(LOCAL_ACTOR,self.id)
        args=(LOCAL_ACTOR,self.id,'request-0001',200,'CNY','c'*64,'Operator','provider-1')
        record=self.store.reconcile(*args)
        self.assertFalse(record['result_recovered']);self.assertFalse(record['automatic_retry'])
        self.assertEqual(record,self.store.reconcile(*args))
        view=self.store.view(LOCAL_ACTOR,self.id)
        self.assertEqual(view['spent'],200);self.assertEqual(view['held'],0);self.assertTrue(view['stopped'])
        with self.assertRaises(BudgetError):self.store.reconcile(*args[:3],201,*args[4:])
        with self.assertRaises(BudgetError):self.store.reconcile(Actor('other','x'),*args[1:])
        with self.assertRaises(BudgetPaused):self.reserve('request-0002')


if __name__=='__main__':unittest.main()
