"""Local-only content review event adapter. No default or implicit paid action."""
import json
import os
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT.parent/'PaperAudit_Coding'/'Code'/'DataCode'))
from finding_explanations import FindingExplanationService
from platform_ports import LOCAL_ACTOR


def main():
    if os.environ.get('PAPER_AUDIT_PLATFORM_MODE','local')!='local':
        raise ValueError('平台身份未接入，拒绝以本地身份运行。')
    # Administrator-provided root; user input cannot choose another filesystem root.
    runtime=os.environ.get('PAPER_AUDIT_RUNTIME_DIR')
    if not runtime:raise ValueError('请由管理员配置已保存检查记录的位置。')
    path=ROOT/'TempData'/'Event.json'
    if path.stat().st_size>16384:raise ValueError('操作内容过大。')
    event=json.loads(path.read_text(encoding='utf-8'))
    if event.get('action')!='status':raise ValueError('独立适配入口只读取状态；付费操作须通过工作台明确确认。')
    if not re.fullmatch(r'[a-f0-9]{12}',str(event.get('scan_id',''))) or not re.fullmatch(r'FD-\d{4}',str(event.get('finding_id',''))):
        raise ValueError('请提供已保存的检查编号及单条线索编号。')
    state=FindingExplanationService(Path(runtime)).view(LOCAL_ACTOR,event['scan_id'],event['finding_id'])
    output=ROOT/'Result';output.mkdir(exist_ok=True)
    (output/'Status.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    return state


if __name__=='__main__':
    main()
