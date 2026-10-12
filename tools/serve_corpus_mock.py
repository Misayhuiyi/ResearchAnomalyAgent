"""Isolated corpus AI software tests. NEVER loads a credential or calls a provider."""
import json
import os
import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mvp-demo'))
from budget_store import MODEL,VERSION
from model_gateway import ENDPOINT,ModelError

if os.environ.get('PAPER_CORPUS_MOCK')!='EXPLICIT_TEST_ONLY':raise SystemExit('Explicit MOCK marker required')
OUT=Path(os.environ['PAPER_CORPUS_RESULTS']).resolve()
if not OUT.is_relative_to(ROOT/'test-results'):raise SystemExit('Isolated results directory required')
runtime=OUT/'mock-runtime'
if runtime.exists():raise SystemExit('Do not overwrite a previous mock run')
runtime.mkdir()
records=json.loads((OUT/'browser-summary.json').read_text(encoding='utf-8'))['cases']
for record in records:
    scan=record['scan_id'];src=OUT/'runtime'/scan;target=runtime/scan
    target.mkdir()
    for name in ('result.json','report.html'):
        shutil.copy2(src/name,target/name)
    # No real quotes, credentials, budgets or model output are copied.
    for name in ('audit','input'):
        shutil.copytree(src/name,target/name)
os.environ['PAPER_AUDIT_RUNTIME_DIR']=str(runtime)
import app
import finding_explanations
REAL_SERVICE=finding_explanations.FindingExplanationService
PRICE={'model':MODEL,'version':VERSION,'currency':'USD','unit':'per_million_tokens',
       'input':'0.30','output':'1.20','reference':'SYNTHETIC MOCK SOFTWARE TEST ONLY'}
CONFIG={'endpoint':ENDPOINT,'price':PRICE,'secret':'SYNTHETIC-NOT-A-KEY','valid_until':time.time()+3600}
calls=[]
baseline=next(r for r in records if r['case_id'].startswith('B01'))
source=json.loads((runtime/baseline['scan_id']/'result.json').read_text(encoding='utf-8'))
failure=next(f for f in source['findings'] if f['id']!=baseline['selected_finding'])
failure_target={'scan_id':baseline['scan_id'],'finding_id':failure['id'],'file':failure['file']}
(OUT/'mock-failure-target.json').write_text(json.dumps(failure_target),encoding='utf-8')


def transport(_secret,body):
    request=json.loads(body);data=json.loads(request['messages'][1]['content'])
    assert len(request['messages'][1]['content'].encode('utf-8'))<=3000
    assert set(data).issubset({'finding_id','type','file','sheet','location','columns','count','relationship','rule','parameters','samples','headers'})
    calls.append({'finding_id':data['finding_id'],'file':data['file'],'input_bytes':len(body),'scope':'MOCK ONLY'})
    (OUT/'mock-transport-record.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
    if data['finding_id']==failure_target['finding_id'] and data['file']==failure_target['file']:
        raise ModelError('模拟服务不可用；原检查结果仍可查看。')
    content={'what':'【模拟响应】'+data['relationship'],'why':'【模拟响应】用于验证本条线索绑定、保存和显示，不是模型质量评估。',
             'benign_explanations':['【模拟响应】可能来自记录精度或明确的公式计算。'],
             'check_steps':['【模拟响应】回到对应文件、工作表和行列核对原记录。'],
             'report_summary':'【模拟响应】待人工复核的数值规律，未确认数据有误。'}
    return {'model':MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content,ensure_ascii=False)}}],
            'usage':{'prompt_tokens':500,'completion_tokens':150}}


if __name__=='__main__':
    with patch.object(app.finding_explanations,'FindingExplanationService',lambda root:REAL_SERVICE(root,lambda:CONFIG,transport)):
        app.run_server('127.0.0.1',8896)
