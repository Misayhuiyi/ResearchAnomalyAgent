"""Recheck already SETTLED model responses with the current safety validator.

No credential loading, network request, payment, budget grant or new reservation.
Recovery is allowed only when the immutable scan/evidence hashes still match.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mvp-demo'))
from finding_explanations import FindingExplanationService,VERSION,PROMPT,minimal_evidence,validate_explanation
from review_store import digest
from platform_ports import LOCAL_ACTOR


def main():
    parser=argparse.ArgumentParser();parser.add_argument('results');args=parser.parse_args();out=Path(args.results).resolve()
    if not out.is_relative_to(ROOT/'test-results'):raise ValueError('Local results required')
    service=FindingExplanationService(out/'runtime',config_loader=lambda: (_ for _ in ()).throw(AssertionError('No credentials allowed')))
    original=json.loads((out/'live-ai-summary.json').read_text(encoding='utf-8'));records=[]
    before_path=out/'live-ai-first-attempt.json'
    if not before_path.exists():before_path.write_bytes((out/'live-ai-summary.json').read_bytes())
    for record in original['records']:
        scan,fid=record['scan_id'],record['finding_id'];row=service._read(LOCAL_ACTOR,scan,fid)
        source_hash,finding=service._finding(LOCAL_ACTOR,scan,fid)
        evidence_hash=digest([VERSION,PROMPT,minimal_evidence(finding)])
        assert source_hash==row['source_hash'] and evidence_hash==row['evidence_hash'],'Immutable binding changed'
        with service.budgets.connect() as db:
            owned=service.budgets.owned(db,LOCAL_ACTOR,row['budget_id'])
            assert owned['binding']==row['binding'],'Budget binding changed'
            call=db.execute('SELECT state,result,actual FROM calls WHERE budget=? AND key=?',(row['budget_id'],'explain-'+fid)).fetchone()
        assert call and call['state']=='settled' and call['result'],'No settled cached response to recover'
        answer=json.loads(call['result']);assert answer.get('usable') is True
        explanation=validate_explanation(answer['content'])
        if row['status']=='failed':
            assert row['message']=='模型解释措辞不符合辅助复核边界，未展示该解释。','Other failures must not be silently changed'
            row.update(status='completed',message='解释仅供人工复核。',explanation=explanation,
                       model={key:answer.get(key) for key in ('requested_model','configured_version','provider_model','elapsed_ms','usage')})
            service._save(LOCAL_ACTOR,scan,fid,row)
            recovery=True
        else:
            assert row['status']=='completed' and row['explanation']==explanation
            recovery=False
        state=service.view(LOCAL_ACTOR,scan,fid)
        record.update(passed=True,state=state,error=None,cached_safety_revalidated=True)
        (out/record['case_id']/'智能解释.json').write_text(json.dumps({'case_id':record['case_id'],'scan_id':scan,'finding_id':fid,'state':state},ensure_ascii=False,indent=2),encoding='utf-8')
        records.append({'case_id':record['case_id'],'recovered':recovery,'passed':True,'paid_calls_added':0,
                        'actual_micros':call['actual'],'latency_ms':answer['elapsed_ms'],'usage':answer['usage']})
    original.update(records=original['records'],passed=sum(r['passed'] for r in original['records']),failed=sum(not r['passed'] for r in original['records']),
                    revalidated_at=datetime.now(timezone.utc).isoformat(),first_attempt_evidence='live-ai-first-attempt.json')
    (out/'live-ai-summary.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'at':datetime.now(timezone.utc).isoformat(),'records':records,'paid_calls_added':0,
            'conservative_cost_micros':sum(r['actual_micros'] for r in records),
            'validator_sha256':hashlib.sha256((ROOT/'mvp-demo/finding_explanations.py').read_bytes()).hexdigest()}
    (out/'cached-revalidation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(records),'recovered':sum(r['recovered'] for r in records),'paid_calls_added':0,'conservative_cost_usd':result['conservative_cost_micros']/1000000},ensure_ascii=False))


if __name__=='__main__':main()
