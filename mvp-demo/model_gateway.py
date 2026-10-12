"""DeepSeek V4.1 Flash adapter. No request without persistent fee authorization.

Official chat-completions contract checked 2026-09-29. Tests inject a transport;
passing tests does not verify provider billing, model quality or live connectivity.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
import time
from pathlib import Path

from budget_store import BudgetError, BudgetPaused, MODEL, VERSION, validate_price
from review_store import digest, encode
from local_credentials import unprotect_secret

ENDPOINT='https://api.deepseek.com'
MAX_RESPONSE=2*1024*1024
MAX_REQUEST_BYTES=24000
PRICE_VALID_UNTIL=1794355200  # 2026-11-11 UTC: administrator must recheck rates.
DEFAULT_PRICE={'model':MODEL,'version':VERSION,'currency':'USD',
               'unit':'per_million_tokens','input':'0.30','output':'1.20',
               'reference':'https://api-docs.deepseek.com/quick_start/pricing/ ; 2026-10-11 peak/cache-miss upper bound'}


class ModelError(ValueError): pass


def load_config(environ=None):
    env=os.environ if environ is None else environ
    location=env.get('PAPER_AUDIT_MODEL_CONFIG','')
    secret=env.get('DEEPSEEK_API_KEY','')
    if not location and not secret and os.name == 'nt' and env.get('LOCALAPPDATA'):
        location=str(Path(env['LOCALAPPDATA'])/'PaperAudit'/'DeepSeek'/'model.json')
    endpoint=env.get('DEEPSEEK_BASE_URL',ENDPOINT).rstrip('/')
    model=env.get('DEEPSEEK_MODEL',MODEL)
    if endpoint!=ENDPOINT or model!=MODEL:
        raise ModelError('模型地址或标识不受支持，请使用官方 DeepSeek V4.1 Flash 配置。')
    if not location and not secret:
        raise ModelError('论文内容复核尚未配置，仍可使用数值检查和人工复核。')
    try:
        if location:
            path=Path(location)
            if path.stat().st_size>16384:raise ValueError()
            config=json.loads(path.read_text(encoding='utf-8'))
        else:
            config={'endpoint':ENDPOINT,'verified_model_name':'DeepSeek-V4.1-Flash',
                    'price':DEFAULT_PRICE,'valid_until':PRICE_VALID_UNTIL}
        if not isinstance(config,dict):raise ValueError()
        if config.get('endpoint')!=ENDPOINT:raise ValueError()
        price=validate_price(config.get('price'))
        # Forces administrators to re-check the moving alias before enabling a release.
        if config.get('verified_model_name')!='DeepSeek-V4.1-Flash':raise ValueError()
        valid_until=config.get('valid_until')
        if type(valid_until) not in (int,float) or not time.time()<valid_until<=time.time()+31*86400:raise ValueError()
        if not secret:secret=unprotect_secret(config.get('protected_secret'))
        if not secret:raise ValueError()
        if len(secret)>1024 or any(ord(c)<33 or ord(c)>126 for c in secret):raise ValueError()
    except (OSError,ValueError,TypeError,BudgetError):
        raise ModelError('模型、价格或有效期配置未通过校验，请联系管理员。') from None
    return {'endpoint':endpoint,'model':model,'price':price,'valid_until':valid_until,'secret':secret}


def http_transport(secret, body):
    """Fixed TLS destination. Retry once only after an explicit HTTP 429 rejection."""
    started=time.monotonic()
    for attempt in range(2):
        connection=http.client.HTTPSConnection('api.deepseek.com',443,timeout=45,context=ssl.create_default_context())
        try:
            connection.request('POST','/chat/completions',body=body,headers={
                'Content-Type':'application/json','Authorization':'Bearer '+secret})
            response=connection.getresponse()
            if response.status==429 and attempt==0:
                time.sleep(.5)
                continue
            if response.status!=200:raise ModelError('模型服务暂不可用，原检查结果不受影响；费用请核对。')
            if 'application/json' not in response.getheader('Content-Type','').lower():raise ModelError('服务返回内容无法核对。')
            chunks=[]; size=0
            while True:
                remaining=45-(time.monotonic()-started)
                if remaining<=0:raise TimeoutError()
                if connection.sock:connection.sock.settimeout(remaining)
                chunk=response.read1(min(65536,MAX_RESPONSE+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                if size>MAX_RESPONSE:raise ModelError('服务返回内容超过本次范围。')
            return json.loads(b''.join(chunks))
        finally:connection.close()
    raise ModelError('模型服务暂不可用。')


class DeepSeekGateway:
    def __init__(self, store, config, transport=None):
        self.store,self.config,self.transport=store,config,transport or http_transport

    def execute(self,actor,budget,binding,key,messages):
        if not isinstance(messages,list) or not 1<=len(messages)<=12 or any(
            not isinstance(m,dict) or set(m)!={'role','content'} or m['role'] not in {'system','user','assistant'}
            or not isinstance(m['content'],str) for m in messages):
            raise ModelError('本次论文复核内容格式无效。')
        state=self.store.view(actor,budget); settings=state['config']
        if (validate_price(self.config['price'])!=settings['price'] or self.config.get('endpoint')!=ENDPOINT
                or self.config.get('model',MODEL)!=MODEL):
            raise BudgetPaused('模型或价格已变化，请重新预估。')
        if time.time()>=self.config.get('valid_until',0) or not self.config.get('secret'):
            raise ModelError('模型配置已失效。')
        body={'model':MODEL,'messages':messages,'max_tokens':settings['max_output'],
              'thinking':{'type':'disabled'},'response_format':{'type':'json_object'},'stream':False}
        raw=encode(body).encode('utf-8')
        # Conservative byte ceiling plus protocol allowance. Reserve the entire configured
        # input limit, not a guessed low average token/character ratio.
        if len(raw)>MAX_REQUEST_BYTES or len(raw)+2048>settings['max_input']:
            raise ModelError('选入的片段超过本次复核容量，请缩小范围。')
        reservation=self.store.reserve(actor,budget,binding,key,digest(body),settings['max_input'],settings['max_output'])
        if not reservation['new']:
            if reservation['state']=='settled' and reservation['result'] is not None:return reservation['result']
            raise BudgetPaused('该请求已提交或费用待核对，不重复调用。')
        if not self.store.claim(actor,budget,key):raise BudgetPaused('该请求正在处理中。')
        started=time.monotonic()
        try:
            answer=self.transport(self.config['secret'],raw)
            usage=answer.get('usage',{}) if isinstance(answer,dict) else {}
            input_tokens,output_tokens=usage.get('prompt_tokens'),usage.get('completion_tokens')
            if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens,output_tokens)<0:
                raise ModelError('调用用量未返回，费用待核对。')
            if max(input_tokens,output_tokens)>1_000_000:raise ModelError('返回用量超出核对范围。')
            valid=False; content=None
            try:
                choice=answer['choices'][0]
                if answer.get('model')!=MODEL or choice['finish_reason']!='stop':raise ValueError()
                content=json.loads(choice['message']['content'])
                if not isinstance(content,dict):raise ValueError()
                valid=True
            except (KeyError,ValueError,IndexError,TypeError):pass
            result={'usable':valid,'content':content if valid else None,'requested_model':MODEL,
                    'configured_version':VERSION,'provider_model':answer.get('model'),
                    'provider_fingerprint':answer.get('system_fingerprint'),
                    'actual_version_verified':False,'usage':{'input':input_tokens,'output':output_tokens},
                    'elapsed_ms':round((time.monotonic()-started)*1000)}
            settled=self.store.settle(actor,budget,key,input_tokens,output_tokens,result)
            if settled['overrun']:raise BudgetPaused('实际用量超过预留，已暂停后续调用，需管理员核对。')
            return result
        except BudgetPaused:raise
        except Exception:
            # Never disclose response text, credentials, document snippets or provider errors.
            self.store.settle(actor,budget,key,result={
                'usable':False,'requested_model':MODEL,
                'elapsed_ms':round((time.monotonic()-started)*1000)})
            raise ModelError('本次论文复核未完成，已保留原结果；调用费用待核对，不自动重试。') from None
