"""Offline maintenance preflight; changes and external replies always require review."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT.parent/'PaperAudit_Coding'/'Code'/'DataCode'))
from delivery_runner import run_local


def main():
    coding=ROOT.parent/'PaperAudit_Coding'
    files={p.relative_to(coding).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (coding/'Code').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    report={'at':datetime.now(timezone.utc).isoformat(),'status':'awaiting_engineer_review',
            'source_hashes':files,'sandbox_reproduction':'not_executed','changes':[],
            'human_review':'required_before_changes','forum_reply':'not_sent',
            'review_gate':{'automatic_changes':False,'automatic_publication':False},
            'rollback':'保留当前时间戳目录；批准后的修改只在新时间戳版本进行，切回旧目录回滚。'}
    out=ROOT/'Result';out.mkdir(exist_ok=True)
    try:
        reproduction=run_local(coding,ROOT/'TempData',out/datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')/'Coding')
        report['reproduction']=reproduction
        report['sandbox_reproduction']=reproduction['status']
        report['issue_category']=reproduction['category']
        report['sandbox_boundary']='本地隔离目录，不是容器或恶意代码安全沙箱；仅执行本交付包固定代码。'
    except Exception:
        report.update(sandbox_reproduction='failed',issue_category='input_or_environment')
    after={p.relative_to(coding).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (coding/'Code').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    report['source_hashes_after']=after
    report['source_unchanged']=files==after
    if files!=after:
        report.update(status='blocked',issue_category='source_changed',sandbox_reproduction='failed')
    (out/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
