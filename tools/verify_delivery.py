"""Run an explicitly selected local candidate on synthetic sample materials.

No Docker, publishing, model requests or external messages are performed.
"""
import hashlib
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=Path(os.environ.get('PAPER_AUDIT_VERIFICATION_DIR',
                             str(ROOT/'docs'/'verification'/'2026-09-30-current'))).resolve()
if not EVIDENCE.is_relative_to(ROOT/'docs'/'verification'):
    raise SystemExit('Verification directory must be inside docs/verification.')
EVIDENCE.mkdir(parents=True,exist_ok=True)
package=Path(os.environ['PAPER_AUDIT_DELIVERY']).resolve()
if package.parent!=ROOT/'delivery' or not package.name.startswith('PaperAudit-'):
    raise SystemExit('Only a candidate under this repository delivery directory can be verified.')
coding=package/'PaperAudit_Coding'
records=[]


def invoke(component,entry,environ=None):
    command=[sys.executable,entry]
    result=subprocess.run(command,cwd=component,env=dict(environ or os.environ,PYTHONUTF8='1'),
                          capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=270)
    records.append({'component':component.name,'command':command,'exit_code':result.returncode,'output':result.stdout,'error':result.stderr})
    if result.returncode:raise RuntimeError(component.name+' 未通过运行检查')
    return result.stdout


try:
    output=Path(invoke(coding,'Code/PaperAudit.py').strip())
    if not output.is_relative_to(coding/'Result'):raise RuntimeError('Output escaped package Result')
    expected=['01.Report/筛查报告.docx','01.Report/筛查报告.pdf','01.Report/筛查报告.html','02.Details/核对明细.xlsx']
    for name in expected:
        if not (output/name).is_file() or (output/name).stat().st_size<100:raise RuntimeError('Missing result: '+name)
    with (output/'InputOutputManifest.csv').open(encoding='utf-8-sig',newline='') as file:
        manifest_rows=list(csv.DictReader(file))
    names={row['path'] for row in manifest_rows}
    if not {'Running_log.txt','PipelineStatus.csv','session_info.txt'}<=names:raise RuntimeError('Manifest omitted runtime outputs')
    for row in manifest_rows:
        path=output/row['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256'] or path.stat().st_size!=int(row['bytes']):raise RuntimeError('Manifest mismatch')
    source=json.loads((output/'Process'/'result.json').read_text(encoding='utf-8'))
    event=package/'PaperAudit_Agent'/'TempData'/'Event.json'
    event.write_text(json.dumps({'action':'status','scan_id':source['scan_id'],
                                'finding_id':source['findings'][0]['id']}),encoding='utf-8')
    runtime=coding/'Data'/'PipeLine'/'01_Scan'/'Result'/output.name
    invoke(package/'PaperAudit_Agent','run.py',dict(os.environ,PAPER_AUDIT_RUNTIME_DIR=str(runtime)))
    run=json.loads(invoke(package/'PaperAudit_AgentRun','run.py'))
    if run['status']!='succeeded' or not run['submitted'] or run['model_calls']!=0:raise RuntimeError('Local execution invalid')
    om=json.loads(invoke(package/'PaperAudit_AgentOM','run.py'))
    if (om['sandbox_reproduction']!='succeeded' or om['forum_reply']!='not_sent' or om['changes']
            or not om['source_unchanged'] or om['review_gate']['automatic_changes']):raise RuntimeError('Maintenance reproduction failed')
    for name,expected_hash in om['source_hashes'].items():
        if hashlib.sha256((coding/name).read_bytes()).hexdigest()!=expected_hash:raise RuntimeError('Maintenance changed source')
    state=json.loads((package/'PaperAudit_Agent'/'Result'/'Status.json').read_text(encoding='utf-8'))
    if state['status']!='not_started':raise RuntimeError('Model should not have run')
    # Refresh only the generated status-event sample, not implementation hashes.
    manifest_path=package/'VersionManifest.txt';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['files'][event.relative_to(package).as_posix()]=hashlib.sha256(event.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
finally:
    evidence={'at':datetime.now(timezone.utc).isoformat(),'package':str(package),'scope':'local synthetic Coding, Agent status, AgentRun execution and AgentOM reproduction; not platform or Docker acceptance','records':records}
    (EVIDENCE/'delivery-runtime.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('Local candidate smoke passed; platform/Docker/paid model/human acceptance NOT EXECUTED.')
