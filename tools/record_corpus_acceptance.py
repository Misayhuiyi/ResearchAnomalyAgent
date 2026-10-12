"""Bind local reports to actual commands, fresh source fingerprints and counts."""
import argparse
import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('results');args=parser.parse_args();out=Path(args.results).resolve()
    if not out.is_relative_to(ROOT/'test-results'):raise ValueError('Local results required')
    unit=(out/'unit-tests-after-fix.log').read_text(encoding='utf-8');match=re.search(r'Ran (\d+) tests in ([\d.]+)s\s+OK',unit)
    assert match,'Final unit suite must actually pass'
    suites=[{'name':'unit and HTTP','total':int(match[1]),'passed':int(match[1]),'failed':0,'seconds':float(match[2]),'evidence':'unit-tests-after-fix.log'}]
    for name,file,key in [('real browser workflow','browser-summary.json','cases'),('independent evidence and exports','evidence-summary.json','records'),
                          ('mock AI','mock-ai-summary.json','records'),('saved real AI browser','saved-ai-browser.json','records')]:
        data=read(out/file);assert data['failed']==0
        suites.append({'name':name,'total':len(data[key]),'passed':data['passed'],'failed':data['failed'],'evidence':file})
    assert read(out/'mock-failure-record.json')['passed']
    suites.append({'name':'mock failure isolation','total':1,'passed':1,'failed':0,'evidence':'mock-failure-record.json'})
    live=read(out/'live-ai-summary.json');cached=read(out/'cached-revalidation.json');initial=read(out/'live-ai-first-attempt.json')
    assert live['provider_calls']==10 and cached['paid_calls_added']==0 and cached['conservative_cost_micros']<=42456
    repeated=ROOT/'test-results/rerun-20261012-050654'
    assert read(repeated/'browser-summary.json')['failed']==0 and read(repeated/'evidence-summary.json')['failed']==0
    fingerprint_files=sorted(set([p for p in (ROOT/'mvp-demo').glob('*.py')]+list((ROOT/'mvp-demo/static').glob('*'))+
                                 list((ROOT/'tools').glob('*corpus*'))+[ROOT/'mvp-demo/tests/test_corpus_tools.py',ROOT/'mvp-demo/tests/test_finding_explanations.py']))
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in fingerprint_files if p.is_file()}
    record={'at':datetime.now(timezone.utc).isoformat(),'baseline_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'candidate':'baseline plus explicitly fingerprinted local changes; no new release claim','platform':platform.platform(),'python':platform.python_version(),
            'suites':suites,'total':sum(s['total'] for s in suites),'passed':sum(s['passed'] for s in suites),'failed':sum(s['failed'] for s in suites),
            'source_hashes':hashes,'manifest_sha256':hashlib.sha256((ROOT/'test-corpus/manifest.json').read_bytes()).hexdigest(),
            'input_manifest_evidence':'test-input-manifest.json (original run); same uploaded material hashes in current manifest',
            'real_calls':10,'first_attempt_passed':initial['passed'],'first_attempt_failed':initial['failed'],
            'cached_recoveries':sum(r['recovered'] for r in cached['records']),'additional_paid_calls_for_recovery':0,
            'approved_max_usd':'0.042456','estimated_10_call_max_usd':'0.035380','conservative_actual_usd':cached['conservative_cost_micros']/1000000,
            'billing_reconciled':False,'human_acceptance':'pending','independent_domain_quality':'not performed',
            'commands':[
                {'command':'python tools/prepare_paper_corpus.py','exit_code':0},
                {'command':'node tools/verify_paper_corpus.cjs','environment':{'DEMO_URL':'http://127.0.0.1:8895/','PAPER_CORPUS_RESULTS':str(out)},'exit_code':0},
                {'command':'python -m unittest discover -s mvp-demo/tests -v','exit_code':0,'evidence':'unit-tests-after-fix.log'},
                {'command':'python tools/check_corpus_evidence.py '+str(out),'exit_code':0},
                {'command':'node tools/verify_corpus_ai.cjs','environment':{'mode':'mock','port':8896},'exit_code':1,'reason':'10 cases passed; initial wording assertion in failure-only branch timed out'},
                {'command':'node tools/verify_corpus_ai.cjs','environment':{'mode':'mock','port':8896,'failure_only':True},'exit_code':0},
                {'command':'node tools/verify_corpus_ai.cjs','environment':{'mode':'live','port':8895,'explicit_user_approval':True,'authorized_micros':42456},'exit_code':1,'reason':'1 of 10 real replies incorrectly rejected by the wording validator'},
                {'command':'python -m unittest discover -s mvp-demo/tests -p test_finding_explanations.py -v','before_fix_exit_code':1,'after_fix_exit_code':0},
                {'command':'python tools/revalidate_corpus_explanations.py '+str(out),'exit_code':0,'paid_calls_added':0},
                {'command':'node tools/verify_corpus_saved_ai.cjs','port':8895,'exit_code':0,'paid_calls_added':0},
                *read(repeated/'commands.json'),
            ],'limits':['Known isolated errors not directly highlighted','Some PDF tables unreadable','No full S1 metabolome/default scan or all-profile cross-product',
                        'Frozen reports do not include finding AI text; separate JSON retained','No repeated provider outputs or expert quality score','Historical dense capacity failure unchanged']}
    (out/'verification-summary.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:record[k] for k in ('total','passed','failed','real_calls','conservative_actual_usd','human_acceptance')},ensure_ascii=False))
if __name__=='__main__':main()
