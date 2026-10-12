"""Isolated end-to-end test server; never contacts DeepSeek or reads credentials."""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mvp-demo'))
if os.environ.get('PAPER_AUDIT_AI_MOCK')!='EXPLICIT_TEST_ONLY':
    raise SystemExit('Mock server requires explicit test marker.')
import app
import finding_explanations
REAL_SERVICE=finding_explanations.FindingExplanationService
from budget_store import MODEL, VERSION
from model_gateway import ENDPOINT

PRICE={'model':MODEL,'version':VERSION,'currency':'USD','unit':'per_million_tokens',
       'input':'0.30','output':'1.20','reference':'SYNTHETIC MOCK ONLY'}
CONFIG={'endpoint':ENDPOINT,'price':PRICE,'secret':'SYNTHETIC-NOT-A-KEY',
        'valid_until':time.time()+7200}
CONTENT={'what':'两列在已检查行中呈现固定差值。',
         'why':'多行重复符合相同关系，值得回原表核对计算方式。',
         'benign_explanations':['可能是按公式生成的派生列。'],
         'check_steps':['核对原始记录、单位和计算公式。'],
         'report_summary':'发现固定差值的待复核统计信号。'}


def transport(_secret, body):
    request=json.loads(body)
    evidence=json.loads(request['messages'][1]['content'])
    if len(request['messages'][1]['content'].encode())>3000 or 'samples' not in evidence:
        raise ValueError('Mock assertion: evidence is not minimal.')
    return {'model':MODEL,'choices':[{'finish_reason':'stop',
             'message':{'content':json.dumps(CONTENT,ensure_ascii=False)}}],
            'usage':{'prompt_tokens':500,'completion_tokens':120}}


def service(root):
    return REAL_SERVICE(root,lambda:CONFIG,transport)


if __name__=='__main__':
    with patch.object(app.finding_explanations,'FindingExplanationService',service):
        app.run_server('127.0.0.1',8881)
