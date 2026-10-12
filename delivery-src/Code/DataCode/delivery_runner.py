"""Bounded local Coding execution in a new workspace, never in the source version."""
import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from delivery_support import validate_inputs
from filesystem_paths import filesystem_path, display_path


def parameter_change(name, old, new):
    # Notes can contain unpublished data. Repair reports retain fingerprints,
    # not research text, while enumerated parameters remain directly reviewable.
    def safe(value):
        if name in {'Profile.txt','Checks.txt','Reference.txt'}:
            return value
        return None if value is None else {'characters':len(value),
            'sha256':hashlib.sha256(value.encode('utf-8')).hexdigest()}
    return {'parameter':name,'before':safe(old),'after':safe(new),
            'reason':'默认值或首尾空白规范化；原输入未修改'}


def run_local(coding, inputs, sandbox):
    if os.environ.get('PAPER_AUDIT_PLATFORM_MODE','local') != 'local':
        raise ValueError('真实平台调度未接入，不能用本地运行代替。')
    uploads, profile, checks, note = validate_inputs(inputs)
    sandbox=filesystem_path(sandbox);sandbox.mkdir(parents=True,exist_ok=False)
    shutil.copytree(Path(coding)/'Code',sandbox/'Code',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['Data','TempData','Result']:(sandbox/name).mkdir()
    target=sandbox/'TempData';(target/'Materials').mkdir()
    for name,data in uploads:(target/'Materials'/name).write_bytes(data)
    repairs=[]
    for name,value in [('Profile.txt',profile),('Checks.txt','\n'.join(checks)),('StudyNote.txt',note)]:
        old=(Path(inputs)/name).read_text(encoding='utf-8-sig') if (Path(inputs)/name).is_file() else None
        if old!=value:repairs.append(parameter_change(name,old,value))
        (target/name).write_text(value,encoding='utf-8')
    command=[sys.executable,'Code/PaperAudit.py']
    try:
        environ={key:value for key,value in os.environ.items()
                 if not key.startswith('DEEPSEEK_') and key!='PAPER_AUDIT_MODEL_CONFIG'}
        completed=subprocess.run(command,cwd=sandbox,env=dict(environ,PYTHONDONTWRITEBYTECODE='1'),
                                 capture_output=True,text=True,encoding='utf-8',timeout=240)
    except subprocess.TimeoutExpired:
        return {'status':'failed','category':'timeout','submitted':True,'repairs':repairs,
                'attempts':1,'retry_limit':0,'message':'本地运行超时，不自动重试。'}
    if completed.returncode:
        # Do not put raw exception strings or paper text into an external summary.
        (sandbox/'Data'/'internal-diagnostic.txt').write_text(
            'Coding exit code: '+str(completed.returncode)+'\nNo raw material or provider response recorded.\n',encoding='utf-8')
        return {'status':'failed','category':'execution','submitted':True,'repairs':repairs,
                'attempts':1,'retry_limit':0,'message':'本地运行失败，请工程师在本机检查诊断。'}
    output=filesystem_path(completed.stdout.strip())
    if not output.is_relative_to(filesystem_path(sandbox/'Result')):raise ValueError('结果路径不在本次工作目录。')
    result=json.loads((output/'Process'/'result.json').read_text(encoding='utf-8'))
    for name in ['01.Report/筛查报告.docx','01.Report/筛查报告.pdf','01.Report/筛查报告.html','02.Details/核对明细.xlsx']:
        if not (output/name).is_file() or (output/name).stat().st_size<100:raise ValueError('本地报告未完整生成。')
    return {'status':'failed' if result['scan_status']=='failed' else 'succeeded','category':'local_coding',
            'submitted':True,'repairs':repairs,'attempts':1,'retry_limit':0,
            'output':display_path(output),'scan_status':result['scan_status'],'model_calls':0,
            'message':'本地 Coding 已运行，实际读取范围及未复核项目见报告；未提交公司平台。'}
