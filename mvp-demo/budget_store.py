"""Persistent, fail-closed per-paper authorization and model-call reservations.

Amounts are integer micro-units of the quoted currency. This module neither knows
API keys nor performs network calls. Only a server-produced quote can be authorized.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path

from review_store import digest, encode

MODEL = 'deepseek-flash'
VERSION = 'DeepSeek V4.1 Flash'


class BudgetError(ValueError): pass
class BudgetPaused(BudgetError): pass


def integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise BudgetError(label+'无效。')
    return value


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > 100000:
            raise ValueError()
        micros = amount * 1_000_000
        if micros != micros.to_integral_value(): raise ValueError()
        return int(micros)
    except (ValueError, InvalidOperation):
        raise BudgetError('金额必须大于零，且不超过六位小数。') from None


def validate_price(price):
    if not isinstance(price, dict) or price.get('model') != MODEL or price.get('version') != VERSION:
        raise BudgetError('指定模型及版本尚未确认，不能开始付费复核。')
    if price.get('currency') not in {'CNY', 'USD'} or price.get('unit') != 'per_million_tokens':
        raise BudgetError('币种或计量单位尚未确认。')
    for key in ['input', 'output']: money(price.get(key))
    if not isinstance(price.get('reference'), str) or not price['reference'].strip():
        raise BudgetError('价格缺少管理员确认的来源或版本。')
    return {key: price[key] for key in ['model','version','currency','unit','input','output','reference']}


def cost(price, input_tokens, output_tokens):
    integer(input_tokens, 0, 1_000_000, '输入用量')
    integer(output_tokens, 0, 1_000_000, '输出用量')
    # Price is currency/million tokens; result is micro-currency.
    amount = Decimal(str(price['input']))*input_tokens + Decimal(str(price['output']))*output_tokens
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


class BudgetStore:
    def __init__(self, root: Path, clock=time.time):
        self.root, self.clock = Path(root), clock
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS budgets (
                id TEXT PRIMARY KEY, tenant TEXT, owner TEXT, binding TEXT, config TEXT,
                cap INTEGER NOT NULL DEFAULT 0, stopped INTEGER NOT NULL DEFAULT 0,
                started REAL, expires REAL);
              CREATE TABLE IF NOT EXISTS quotes (
                id TEXT PRIMARY KEY, budget TEXT, cap INTEGER, expires REAL, authorized INTEGER DEFAULT 0);
              CREATE TABLE IF NOT EXISTS grants (
                budget TEXT, key TEXT, quote TEXT, amount INTEGER, at REAL, PRIMARY KEY(budget,key));
              CREATE TABLE IF NOT EXISTS calls (
                budget TEXT, key TEXT, signature TEXT, reserved INTEGER, actual INTEGER,
                state TEXT, requested REAL, result TEXT, PRIMARY KEY(budget,key));
              CREATE TABLE IF NOT EXISTS reconciliations (
                budget TEXT, call_key TEXT, signature TEXT, record TEXT,
                PRIMARY KEY(budget,call_key));
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.root/'budgets.sqlite3', timeout=15); db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def key(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',value):
            raise BudgetError('操作凭据无效。')

    @staticmethod
    def owned(db,actor,budget):
        row=db.execute('SELECT * FROM budgets WHERE id=? AND tenant=? AND owner=?',
                       (budget,actor.tenant,actor.subject)).fetchone()
        if not row: raise BudgetError('费用记录不存在或无权访问。')
        return row

    def create(self, actor, material_hash, scope_hash, price, max_calls=30, max_input=32000,
               max_output=4000, max_seconds=900, valid_seconds=86400):
        for value in [material_hash,scope_hash]:
            if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
                raise BudgetError('材料或复核范围版本无效。')
        price=validate_price(price)
        config={'price':price, 'max_calls':integer(max_calls,1,30,'调用次数'),
                'max_input':integer(max_input,1,128000,'输入上限'),
                'max_output':integer(max_output,1,32000,'输出上限'),
                'max_seconds':integer(max_seconds,1,3600,'运行时限')}
        integer(valid_seconds,1,86400,'授权有效期')
        binding=digest([material_hash,scope_hash,config])
        budget=uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO budgets(id,tenant,owner,binding,config,expires) VALUES(?,?,?,?,?,?)',
                       (budget,actor.tenant,actor.subject,binding,encode(config),self.clock()+valid_seconds))
        return {'budget_id':budget,'binding':binding,**config}

    @staticmethod
    def totals(db,budget):
        row=db.execute('''SELECT COALESCE(SUM(CASE WHEN state='settled' THEN actual ELSE 0 END),0) spent,
                         COALESCE(SUM(CASE WHEN state IN ('reserved','dispatched','uncertain') THEN reserved ELSE 0 END),0) held,
                         COUNT(*) count FROM calls WHERE budget=?''',(budget,)).fetchone()
        return dict(row)

    def quote(self,actor,budget,cumulative_cap):
        cap=money(cumulative_cap)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,actor,budget); totals=self.totals(db,budget)
            if row['stopped'] or self.clock()>=row['expires']: raise BudgetPaused('复核已停止或授权已过期。')
            if cap<=row['cap'] or cap<totals['spent']+totals['held']:
                raise BudgetError('新的累计上限须高于原授权，且覆盖已用和待核对费用。')
            quote=uuid.uuid4().hex
            db.execute('INSERT INTO quotes(id,budget,cap,expires) VALUES(?,?,?,?)',
                       (quote,budget,cap,min(row['expires'],self.clock()+1800)))
            return {'quote_id':quote,'budget_id':budget,'currency':json.loads(row['config'])['price']['currency'],
                    'spent_micros':totals['spent'],'held_micros':totals['held'],
                    'previous_cap_micros':row['cap'],'additional_micros':cap-row['cap'],'cap_micros':cap,
                    'binding':row['binding']}

    def authorize(self,actor,budget,quote,key,confirmed):
        self.key(key)
        if confirmed is not True: raise BudgetError('请先确认本篇论文的最高费用。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,actor,budget)
            prior=db.execute('SELECT * FROM grants WHERE budget=? AND key=?',(budget,key)).fetchone()
            if prior:
                if prior['quote']!=quote: raise BudgetError('同一次确认不能对应不同预估。')
                return prior['amount']
            q=db.execute('SELECT * FROM quotes WHERE id=? AND budget=?',(quote,budget)).fetchone()
            if not q or q['authorized'] or q['expires']<=self.clock() or row['stopped'] or q['cap']<=row['cap']:
                raise BudgetPaused('本次预估已失效，请重新确认。')
            db.execute('UPDATE quotes SET authorized=1 WHERE id=?',(quote,))
            db.execute('UPDATE budgets SET cap=? WHERE id=?',(q['cap'],budget))
            db.execute('INSERT INTO grants VALUES(?,?,?,?,?)',(budget,key,quote,q['cap'],self.clock()))
            return q['cap']

    def reserve(self,actor,budget,binding,key,request_hash,input_max,output_max):
        self.key(key)
        if not isinstance(request_hash,str) or not re.fullmatch('[a-f0-9]{64}',request_hash):
            raise BudgetError('请求内容校验无效。')
        signature=digest([binding,request_hash,input_max,output_max])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,actor,budget)
            if row['binding']!=binding: raise BudgetPaused('材料、复核范围或模型计价已变化，需要重新预估。')
            prior=db.execute('SELECT * FROM calls WHERE budget=? AND key=?',(budget,key)).fetchone()
            if prior:
                if prior['signature']!=signature: raise BudgetError('同一请求凭据不能用于不同内容。')
                return {'new':False,'state':prior['state'],'reserved_micros':prior['reserved'],
                        'result':json.loads(prior['result']) if prior['result'] else None}
            config=json.loads(row['config']); totals=self.totals(db,budget)
            integer(input_max,1,config['max_input'],'输入上限'); integer(output_max,1,config['max_output'],'输出上限')
            if row['stopped'] or self.clock()>=row['expires']: raise BudgetPaused('复核已停止或授权已过期。')
            if row['started'] is not None and self.clock()-row['started']>=config['max_seconds']:
                raise BudgetPaused('已达到本次复核时限，保留已有结果。')
            if totals['count']>=config['max_calls']: raise BudgetPaused('已达到本篇论文的调用次数上限。')
            reserved=cost(config['price'],input_max,output_max)
            if totals['spent']+totals['held']+reserved>row['cap']:
                raise BudgetPaused('当前额度不足，请确认追加费用后继续。')
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,?,?,?)',
                       (budget,key,signature,reserved,None,'reserved',self.clock(),None))
            db.execute('UPDATE budgets SET started=COALESCE(started,?) WHERE id=?',(self.clock(),budget))
            return {'new':True,'state':'reserved','reserved_micros':reserved,'result':None}

    def claim(self,actor,budget,key):
        """Exactly one worker may send. Restart never reclaims an already dispatched request."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); row=self.owned(db,actor,budget)
            if row['stopped'] or self.clock()>=row['expires']: raise BudgetPaused('复核已停止或授权已过期。')
            config=json.loads(row['config'])
            if row['started'] is not None and self.clock()-row['started']>=config['max_seconds']:
                raise BudgetPaused('已达到本次复核时限。')
            changed=db.execute("UPDATE calls SET state='dispatched' WHERE budget=? AND key=? AND state='reserved'",(budget,key))
            return changed.rowcount==1

    def settle(self,actor,budget,key,input_tokens=None,output_tokens=None,result=None,definitely_unbilled=False):
        """Uncertain billing retains reservation; known overruns are recorded and stop dispatch."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); row=self.owned(db,actor,budget)
            call=db.execute('SELECT * FROM calls WHERE budget=? AND key=?',(budget,key)).fetchone()
            if not call or call['state'] not in {'dispatched','uncertain'}: raise BudgetError('该请求不能重复结算。')
            if definitely_unbilled:
                actual=0; state='settled'
            elif input_tokens is None or output_tokens is None:
                actual=None; state='uncertain'
            else:
                actual=cost(json.loads(row['config'])['price'],input_tokens,output_tokens); state='settled'
            db.execute('UPDATE calls SET state=?,actual=?,result=? WHERE budget=? AND key=?',
                       (state,actual,encode(result) if result is not None else None,budget,key))
            if actual is not None and actual>call['reserved']:
                db.execute('UPDATE budgets SET stopped=1 WHERE id=?',(budget,))
            return {'state':state,'actual_micros':actual,'overrun':actual is not None and actual>call['reserved']}

    def cancel(self,actor,budget):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); self.owned(db,actor,budget)
            db.execute('UPDATE budgets SET stopped=1 WHERE id=?',(budget,))
            # A reserved request has not been claimed/sent; in-flight charges cannot be undone.
            db.execute("UPDATE calls SET state='settled',actual=0 WHERE budget=? AND state='reserved'",(budget,))

    def recover(self,actor,budget):
        with self.connect() as db:
            self.owned(db,actor,budget)
            db.execute("UPDATE calls SET state='uncertain' WHERE budget=? AND state='dispatched'",(budget,))

    def reconcile(self, actor, budget, key, actual_micros, currency, receipt_sha256, reviewer, reference):
        """Offline operator boundary, deliberately NOT exposed by the HTTP server.

        A verified provider bill resolves accounting only, never synthesizes a
        missing model response or retries that request. The old plan stays stopped.
        """
        self.key(key)
        integer(actual_micros, 0, 100000_000000, '实付金额')
        if not isinstance(receipt_sha256, str) or not re.fullmatch('[a-f0-9]{64}', receipt_sha256):
            raise BudgetError('缺少账单文件校验。')
        if any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 200 for x in [reviewer, reference]):
            raise BudgetError('须记录核对人和服务方账单编号。')
        record = {'actual_micros':actual_micros, 'currency':currency, 'receipt_sha256':receipt_sha256,
                  'reviewer':reviewer.strip(), 'reference':reference.strip()}
        signature=digest(record)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=self.owned(db,actor,budget)
            if currency != json.loads(row['config'])['price']['currency']:
                raise BudgetError('账单币种与原授权不一致。')
            prior=db.execute('SELECT * FROM reconciliations WHERE budget=? AND call_key=?',(budget,key)).fetchone()
            if prior:
                if prior['signature'] != signature: raise BudgetError('已对账记录不能被不同账单覆盖。')
                return json.loads(prior['record'])
            call=db.execute('SELECT * FROM calls WHERE budget=? AND key=?',(budget,key)).fetchone()
            if not call or call['state'] != 'uncertain':
                raise BudgetError('只能处理已停止等待核账的请求。')
            record.update(at=self.clock(), previous_reserved_micros=call['reserved'],
                          result_recovered=False, automatic_retry=False)
            db.execute("UPDATE calls SET state='settled',actual=? WHERE budget=? AND key=?",(actual_micros,budget,key))
            db.execute('UPDATE budgets SET stopped=1 WHERE id=?',(budget,))
            db.execute('INSERT INTO reconciliations VALUES(?,?,?,?)',(budget,key,signature,encode(record)))
            return record

    def view(self,actor,budget):
        with self.connect() as db:
            row=self.owned(db,actor,budget)
            return {'budget_id':budget,'cap_micros':row['cap'],'stopped':bool(row['stopped']),
                    'expires':row['expires'],'binding':row['binding'],'config':json.loads(row['config']),**self.totals(db,budget)}
