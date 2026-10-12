"""Validate then execute Coding locally in a fresh workspace; no external submission."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
CORE=ROOT.parent/'PaperAudit_Coding'/'Code'/'DataCode'
sys.path.insert(0,str(CORE))
from delivery_support import validate_inputs
from delivery_runner import run_local


def main():
    result=ROOT/'Result';result.mkdir(exist_ok=True)
    report={'at':datetime.now(timezone.utc).isoformat(),'submitted':False,'repairs':[],
            'retry_limit':0,'forum_status':'未提交；需经授权渠道确认后发送脱敏摘要'}
    try:
        uploads,profile,checks,note=validate_inputs(ROOT/'TempData')
        report.update(run_local(ROOT.parent/'PaperAudit_Coding',ROOT/'TempData',
                      result/datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')/'Coding'))
        report.update(file_count=len(uploads),profile=profile,checks=checks)
    except Exception as exc:
        report.update(status='blocked',category='input_or_environment',message=str(exc))
    # Every invocation has its own result; previous diagnostic reports are retained.
    path=result/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.json')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
