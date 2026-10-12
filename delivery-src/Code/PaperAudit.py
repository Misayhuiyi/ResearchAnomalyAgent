"""Baiyin batch entry. User inputs are read only from sibling TempData."""
import csv
import hashlib
import json
import os
import platform
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent/'DataCode'))
from PipeLine.PaperConan import scan_materials
from platform_ports import LOCAL_ACTOR
from review_store import ReviewStore
from report_exports import export_snapshot, download_path
from delivery_support import validate_inputs
from filesystem_paths import filesystem_path, display_path


def PaperAudit():
    coding=filesystem_path(Path(__file__).resolve().parent.parent)
    # A batch has no browser identity. Platform publication must provide an approved
    # identity/storage adapter, not an arbitrary tenant value from TempData.
    if os.environ.get('PAPER_AUDIT_PLATFORM_MODE','local')!='local':
        raise RuntimeError('平台适配尚未启用，不能以本地身份处理平台任务。')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    output=coding/'Result'/stamp;output.mkdir(parents=True,exist_ok=False)
    status=[]
    try:
        uploads,profile,checks,note=validate_inputs(coding/'TempData')
        first=coding/'Data'/'PipeLine'/'01_Scan'
        stage=first/'TempData'/stamp;stage.mkdir(parents=True,exist_ok=False)
        materials=stage/'Materials';materials.mkdir()
        for name,data in uploads:(materials/name).write_bytes(data)
        (stage/'Profile.txt').write_text(profile,encoding='utf-8')
        (stage/'Checks.txt').write_text('\n'.join(checks),encoding='utf-8')
        (stage/'StudyNote.txt').write_text(note,encoding='utf-8')
        process=first/'Result'/stamp
        result=scan_materials(stage,process)
        status.append(['01_Scan',result['scan_status'],'数值检查结束，实际覆盖见报告'])
        second=coding/'Data'/'PipeLine'/'02_Report'
        report_input=second/'TempData'/stamp;report_input.mkdir(parents=True,exist_ok=False)
        shutil.copy2(process/'result.json',report_input/'result.json')
        report_output=second/'Result'/stamp;report_output.mkdir(parents=True,exist_ok=False)
        store=ReviewStore(process);store.register(LOCAL_ACTOR,result)
        snapshot=store.freeze(LOCAL_ACTOR,result['scan_id'],0,'batch-report-0001',
                              {'status':'not_started','message':'本次数值批处理未进行付费内容核对。'})
        export_snapshot(store,LOCAL_ACTOR,snapshot)
        report_dir=output/'01.Report';report_dir.mkdir()
        detail_dir=output/'02.Details';detail_dir.mkdir()
        for file in ['report.docx','report.pdf','report.html','details.xlsx']:
            target=detail_dir/'核对明细.xlsx' if file.endswith('.xlsx') else report_dir/('筛查报告'+Path(file).suffix)
            shutil.copy2(download_path(store,LOCAL_ACTOR,snapshot['report_id'],file),target)
            shutil.copy2(target,report_output/target.name)
        evidence=output/'03.Evidence';evidence.mkdir()
        (evidence/'evidence.json').write_text(json.dumps({'material_sources':result.get('material_sources',[]),
            'findings':result['findings'],'study_note':note,'study_note_source':'用户说明，未修改原始证据'},ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'Process').mkdir();shutil.copy2(report_input/'result.json',output/'Process'/'result.json')
        (output/'FinalResults').mkdir()
        (output/'FinalResults'/'summary.json').write_text(json.dumps({'scan_status':result['scan_status'],
            'finding_count':len(result['findings']),'reviewed':False,'model_used':False},ensure_ascii=False),encoding='utf-8')
        (output/'Figures').mkdir();(output/'Figures'/'说明.txt').write_text('本应用不生成统计图，请查看原始数值和证据对照。',encoding='utf-8')
        (output/'Reports').mkdir()
        (output/'Reports'/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>报告下载</title><h1>报告下载</h1><p><a href="../01.Report/筛查报告.html">查看报告</a></p><p><a href="../01.Report/筛查报告.docx">Word</a> · <a href="../01.Report/筛查报告.pdf">PDF</a> · <a href="../02.Details/核对明细.xlsx">Excel 明细</a></p>',encoding='utf-8')
        for step,source_in,source_out in [('01_Scan',stage,process),('02_Report',report_input,report_output)]:
            shutil.copytree(source_in,output/'PipeLine'/step/'TempData')
            shutil.copytree(source_out,output/'PipeLine'/step/'Result')
        status.append(['02_Report','complete','四种格式来自同一冻结版本，尚未人工复核'])
        (output/'Running_log.txt').write_text('本次数值检查和报告生成完成。模型调用：未执行。人工复核：未执行。\n',encoding='utf-8')
        return display_path(output)
    except Exception:
        status.append(['workflow','failed','处理未完成，未将已有文件标为完整交付'])
        (output/'Running_log.txt').write_text('处理未完成。请核对输入范围、依赖与内部诊断；没有发起付费调用。\n',encoding='utf-8')
        raise
    finally:
        with (output/'PipelineStatus.csv').open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.writer(file);writer.writerow(['step','status','message']);writer.writerows(status)
        (output/'session_info.txt').write_text('Python '+platform.python_version()+'\n'+platform.system()+'\n',encoding='utf-8')
        # Write the manifest last so diagnostic/status files are covered too.
        with (output/'InputOutputManifest.csv').open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.writer(file);writer.writerow(['path','sha256','bytes'])
            for path in sorted(output.rglob('*')):
                if path.is_file() and path.name!='InputOutputManifest.csv':
                    writer.writerow([path.relative_to(output).as_posix(),hashlib.sha256(path.read_bytes()).hexdigest(),path.stat().st_size])


if __name__=='__main__':
    print(PaperAudit())
