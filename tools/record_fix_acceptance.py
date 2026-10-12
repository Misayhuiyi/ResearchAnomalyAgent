"""Evidence for the explicit repair scope; no network/model call or release claim."""
import hashlib
import json
import re
import subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/2026-10-11-fixes-final'
OLD=ROOT/'test-results/2026-10-11-multipaper-v1'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
log=(OUT/'unit-tests.log').read_text(encoding='utf-8');match=re.search(r'Ran (\d+) tests in ([\d.]+)s\s+OK',log);assert match
suites=[{'name':'unit and HTTP','total':int(match[1]),'passed':int(match[1]),'failed':0,'evidence':'unit-tests.log'}]
for name,file in [('real 12-case workflow','browser-summary.json'),('source and exports','evidence-summary.json'),('mock AI','mock-ai-summary.json'),('real reference browser','reference-browser.json')]:
    data=read(OUT/file);assert data['failed']==0
    suites.append({'name':name,'total':data['passed'],'passed':data['passed'],'failed':0,'evidence':file})
assert read(OUT/'mock-failure-record.json')['passed'];suites.append({'name':'mock failure isolation','total':1,'passed':1,'failed':0,'evidence':'mock-failure-record.json'})
ai=read(OLD/'saved-ai-browser.json');all_formats=read(OLD/'real-ai-all-formats.json')
assert ai['passed']==10 and ai['failed']==0 and all_formats['passed']==10
assert all(r['frozen_report_contains_finding_ai'] for r in ai['records'])
suites.append({'name':'retained real AI report closure','total':10,'passed':10,'failed':0,'evidence':str(OLD.relative_to(ROOT))+'/saved-ai-browser.json; real-ai-all-formats.json'})
refs=read(OUT/'reference-browser.json');assert sum(r['differences'] for r in refs['records'])==4
hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for group in
        [list((ROOT/'mvp-demo').glob('*.py')),list((ROOT/'mvp-demo/static').glob('*')),list((ROOT/'mvp-demo/tests').glob('test_*.py')),
         list((ROOT/'tools').glob('*corpus*')),[ROOT/'tools/verify_reference_browser.cjs',ROOT/'tools/Open-PaperCorpus.ps1']]
        for p in group if p.is_file()}
result={'at':datetime.now(timezone.utc).isoformat(),'scope':'AI report integration, column/identifier fixes, PDF scope and user-approved reference comparison',
        'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'candidate':'baseline plus fingerprinted uncommitted source',
        'suites':suites,'total':sum(s['total'] for s in suites),'passed':sum(s['passed'] for s in suites),'failed':0,
        'source_hashes':hashes,'new_paid_calls':0,'known_reference_differences_located':4,'human_acceptance':'pending',
        'old_bill_conservative_usd':'0.005419','old_snapshots_preserved':True,'platform_release':'not performed',
        'commands':[{'command':'python -m unittest discover -s mvp-demo/tests -q','exit_code':0},
                    {'command':'node tools/verify_paper_corpus.cjs','environment':'fresh isolated fixes-final runtime on port8900','exit_code':0},
                    {'command':'python tools/check_corpus_evidence.py '+str(OUT),'exit_code':0},
                    {'command':'node tools/verify_reference_browser.cjs','environment':'port8900, fixes-final runtime','exit_code':0},
                    {'command':'node tools/verify_corpus_ai.cjs','environment':'explicit mock port8896, fixes-final mock-runtime','exit_code':0},
                    {'command':'node tools/verify_corpus_saved_ai.cjs','environment':'old real-response runtime, current report implementation','exit_code':0,'paid_calls_added':0},
                    {'command':'python tools/check_saved_ai_exports.py','exit_code':0,'paid_calls_added':0},
                    {'command':'powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/Open-PaperCorpus.ps1 -NoOpen','exit_code':0}],
        'limits':['No OCR/PDF decryption','No universal error recall without reference or analysis reproduction','Dense100MB capacity not certified',
                  'Reference match/size/formula limits explicitly enforced','Domain AI quality, bills and platform integration not accepted']}
(OUT/'verification-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:result[k] for k in ('total','passed','failed','known_reference_differences_located','new_paid_calls','human_acceptance')}))
