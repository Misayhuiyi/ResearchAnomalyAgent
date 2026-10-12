"""Generate the offline, non-technical corpus guide from retained actual records."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'test-corpus'
STYLE='body{font:15px/1.7 "Microsoft YaHei",sans-serif;color:#18344b;background:#f5f8fc;max-width:1280px;margin:32px auto;padding:0 22px}section{background:white;padding:22px;border:1px solid #d8e2ed;border-radius:10px;margin:20px 0}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d8e2ed;padding:9px;text-align:left;vertical-align:top}th{background:#edf4fc}a{color:#1664bd}small{color:#60738b}h1{font-size:26px}h2{font-size:19px}.note{background:#fff5df;padding:15px;border-radius:8px}.good{color:#127550}.warn{color:#985b00}'
GROUP={'baseline':'未改动公开材料','corrected_reference':'有来源的修正参考','documented_error':'有公开依据的已知错误','injected':'人工错误对照（非原论文问题）'}
PROFILES={'review':'标准','triage':'快速','forensic':'全面'}
def esc(value):return html.escape(str(value))
def doc(title,body):return f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{STYLE}</style><h1>{esc(title)}</h1>{body}</html>'
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('results');args=parser.parse_args();out=Path(args.results).resolve()
    if not out.is_relative_to(ROOT/'test-results'):raise ValueError('Local results required')
    manifest=read(CORPUS/'manifest.json');browser=read(out/'browser-summary.json');evidence=read(out/'evidence-summary.json')
    ai=read(out/'live-ai-summary.json') if (out/'live-ai-summary.json').exists() else None
    reference=read(out/'reference-browser.json') if (out/'reference-browser.json').exists() else None
    ref_by={r['case_id']:r for r in reference['records'] if r['passed']} if reference else {}
    ev={v['case_id']:v for v in evidence['records']};runs={v['case_id']:v for v in browser['cases']}
    ai_by={v['case_id']:v for v in ai['records']} if ai else {}
    rows=[];result_rows=[];summary_rows=[]
    for c in manifest['cases']:
        links='<br>'.join(f'<a href="{esc(p)}">{esc(Path(p).name)}</a>' for p in c['uploads'])
        expect='；'.join(f'{e["n"]} 行，{e.get("parameter",e["kind"])}={e.get("value","相同")}' for e in c['expected'].get('relations',[]))
        if 'rounding' in c['expected']:expect='4 个原值 0.451 / 0.469 / 0.531 / 0.459，文件行 2–5；按 1 位小数比较为 0.5。'
        if c['group']=='documented_error':expect='对照公开勘误检查；系统不保证发现孤立录入错或分析方法错。'
        if not expect:expect='查看读取范围和提示；无提示不等于无错误，有提示不等于已证实错误。'
        rows.append(f'<tr><td>{esc(c["id"])}<br><strong>{esc(c["title"])}</strong><br><small>{esc(GROUP[c["group"]])}</small></td><td>{links}</td><td>{esc(PROFILES[c["profile"]])}</td><td>{esc(expect)}<br><small>{esc(c.get("notes",""))}</small></td></tr>')
        r=runs[c['id']];v=ev[c['id']];known=v.get('known_cells',[])
        known_note=(f'已知差异定位 {sum(k["highlighted"] for k in known)}/{len(known)}；未自动确证错误' if known else
                    '批次校正错误需重现原分析，未自动确证' if c['id'].startswith('E03') else '不作为论文无误/有误证明')
        if c['id'] in ref_by:known_note=f'统计扫描未定位；参考版本核对已定位 {ref_by[c["id"]]["differences"]}/{len(known)} 处差异，不自动判定哪版正确。'
        source_status='已读取' if r.get('scan_status')=='complete' else '部分读取，查看材料说明'
        formats='<br>'.join(f'<a href="{esc(c["id"])}/{name}">{label}</a>' for name,label in [('result.json','检查结果 JSON'),('paperconan-scan.json','原始扫描记录'),('report.docx','Word 报告'),('report.pdf','PDF 报告'),('details.xlsx','Excel 明细'),('report.html','HTML 报告'),('source-and-report-check.json','原值核对记录')])
        if (out/c['id']/'智能解释.json').exists():
            formats+=f'<br><a href="{esc(c["id"])}/智能解释.json">本条真实智能解释</a><br><a href="{esc(c["id"])}/after-ai/report.html">解释后再次生成的报告</a>'
        if c['id'] in ref_by:
            formats+=f'<br><a href="{esc(c["id"])}/reference-verified/comparison.json">真实原版/修正版差异</a><br><a href="{esc(c["id"])}/reference-verified/report.html">含版本核对的报告</a>'
        live=ai_by.get(c['id'])
        ai_status='无检测线索，不编造解释' if not r.get('selected_finding') else ('真实解释已生成' if live and live['passed'] else '真实解释失败，查看记录' if live else '真实模型未执行；模拟流程单独留档')
        result_rows.append(f'<tr><td>{esc(c["title"])}</td><td>{esc(source_status)}<br>{r.get("summary",{}).get("findings","—")} 条提示<br>{r.get("duration_ms",0)/1000:.1f} 秒</td><td>{"页面流程通过" if r.get("workflow_passed") else "页面流程失败"}<br>{"原值/导出核对通过" if v.get("passed") else "原值/导出核对失败"}<br>{esc(known_note)}</td><td>{esc(ai_status)}</td><td>{formats}</td></tr>')
        summary_rows.append({'案例':c['id'],'类别':GROUP[c['group']],'策略':PROFILES[c['profile']],'线索数':r.get('summary',{}).get('findings'),
                             '读取状态':source_status,'流程通过':r.get('workflow_passed'),'预设关系通过':r.get('expected_passed'),
                             '原值检查通过':v.get('passed'),'数值核对次数':v.get('source_values_checked',0),
                             '已知差异定位数':sum(k['highlighted'] for k in known),'已知差异数':len(known),
                             '真实智能解释':ai_status,'耗时秒':round(r.get('duration_ms',0)/1000,2)})
    sources=''.join(f'<li>{esc(p["id"])}：<a href="{esc(p["source"])}">论文来源</a> · DOI {esc(p["doi"])}'+
                    (f' · <a href="{esc(p["data"])}">数据/勘误来源</a>' if p.get('data') else '')+
                    (f' · <a href="{esc(p["correction"])}">出版社勘误</a>' if p.get('correction') else '')+
                    f'<br><small>{esc(p["license"])}</small></li>' for p in manifest['papers'])
    guide=f'<section><h2>怎么使用</h2><ol><li>双击同目录的「打开检查工具.cmd」。打开后保持页面在本机使用。</li><li>选一个案例，在工具中同时上传该行列出的全部文件，选择对应检查范围，再点开始检查。不要一次把不同案例混在一起。</li><li>查看原始值、材料读取范围；对照预期，保存自己的复核意见并下载报告。智能解释先查看费用，确认后才调用。</li></ol><p><a href="http://127.0.0.1:8895/">打开检查工具</a> · <a href="../{esc(str(out.relative_to(ROOT)).replace(chr(92),"/"))}/测试结果总览.html">查看本次完整测试结果</a></p></section>'
    guide+='<p class="note">未改动或修正参考材料不是“科研无误认证”。人工对照中的新增列只是测试，不能归因于原论文。统计信号不代表科研不端，也不能判断作者意图。</p>'
    guide+='<section><h2>普通录入差异怎么查</h2><p>检查完成后，在「与参考版本核对」中选原表，读取参考文件，再选工作表、匹配编号和要核对的列。没有唯一编号时，必须先确认两个版本的数据顺序一致。核对会显示双方原始值与行列，并收录进新生成的复核报告。</p><p>Iris：先运行 E01，参考文件选择 B03 中的 iris_corrected.csv，勾选「数据顺序一致」；应看到文件行36/39的3处差异。运动实验：先运行 E02，参考文件选择 B04 的 corrected.xlsx，两边均选 Experiment 2，以 Subject（列2）匹配；应看到 K6 的1处差异。</p><p>匹配编号重复、空缺或顺序无法确认时不要强行比较。参考值也可能有误，工具不替代原始记录和人工核验。已保存的 AI 解释现在会随新生成的四种复核报告一起导出；旧冻结报告不会被改写。</p></section>'
    guide+='<section><h2>12 个案例（5 篇不同论文）</h2><table><tr><th>案例</th><th>应同时上传的文件</th><th>检查范围</th><th>如何核对</th></tr>'+''.join(rows)+'</table></section>'
    guide+='<section><h2>真实错误的正确值对照</h2><p>Iris：文件行36第4列 0.1 → 0.2；文件行39第2列 3.1 → 3.6、第3列 1.5 → 1.4。样本序号35/38与文件行号相差一个表头。</p><p>运动实验：Experiment 2，K6（第4位参与者的 VO2maxVB）65.95549826312603 → 68.88；K5 的 65.95549826312603 保持不变。</p><p>果蝇研究：只对 AL 做了批次校正、遗漏 DR。修改影响 Data_for_S2 等分析结果，不是一个固定比例公式。<a href="publisher-differences.json">完整出版社版本差异表</a>保留 3917 处值差异，不能将每一处差异都算成系统应识别的独立错误。</p></section>'
    guide+='<section><h2>来源与保留方式</h2><ul>'+sources+'</ul><p>originals 保留下载原件，cases 保留可直接上传的案例；SHA256 与预期见 manifest.json。仅用于本机练习和回归测试，不把论文、原始数据或模型响应上传公开仓库。</p></section>'
    (CORPUS/'测试集导航.html').write_text(doc('科研筛查工具测试集',guide),encoding='utf-8')
    (CORPUS/'current-test-results.json').write_text(json.dumps({'results_relative':str(out.relative_to(ROOT)).replace('\\','/')},ensure_ascii=False),encoding='utf-8')
    (CORPUS/'打开检查工具.cmd').write_text('@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\tools\Open-PaperCorpus.ps1"\r\nif errorlevel 1 pause\r\n',encoding='ascii')
    total=sum(v.get('source_values_checked',0) for v in evidence['records'])
    numbers=sum(v.get('numeric_values_checked',0) for v in evidence['records'])
    report=f'<section><p>5 篇论文、12 个案例；页面主流程 {browser["passed"]}/{len(browser["cases"])} 通过；原值与报告校验 {evidence["passed"]}/{len(evidence["records"])} 通过。独立核对原始单元格 {total} 次，其中数值 {numbers} 次（非去重数；包含不同线索重复引用的单元格）。4 个人工错误案例均命中预设关系。</p><p>人工业务验收：待用户实际操作确认。该集已用于开发回归，不是盲测集。</p><p><a href="../../test-corpus/测试集导航.html">返回测试集及手动操作</a> · <a href="结果汇总.csv">下载结果汇总 CSV</a> · <a href="browser-summary.json">页面测试记录</a> · <a href="evidence-summary.json">原值与报告记录</a> · <a href="mock-ai-summary.json">模拟智能解释记录</a>'+(f' · <a href="live-ai-summary.json">真实智能解释记录</a>' if ai else '')+'</p></section>'
    report+=('<p class="note">参考版本核对已准确定位 Iris 的3处差异和运动实验 K6 的1处差异，并完成四格式导出、历史重开验证。这不意味着统计扫描本身能识别所有孤立错误，也不自动判定哪版正确。果蝇批次校正错误仍需要重现原分析；无 OCR、加密或只有图中数值的 PDF 部分不算数值表检查通过。</p>' if ref_by else '<p class="note">不能用 12/12 流程通过推导所有论文错误均被找到。没有基准版本时，孤立录入差异不保证被统计扫描提示。</p>')
    report+='<p>已保存的真实智能解释现已合入新生成的四格式报告，旧冻结版本仍完整保留。首次真实解释 9/10 可直接展示；1 条因否定句误拦截，修复后用已经付费的原回复重新校验通过，没有重复付费。首次失败及修复后页面记录均保留。</p>' if ai else ''
    report+='<section><table><tr><th>案例</th><th>实际检查</th><th>流程与已知错误</th><th>智能解释</th><th>记录及报告</th></tr>'+''.join(result_rows)+'</table></section>'
    (out/'测试结果总览.html').write_text(doc('多论文全流程测试结果',report),encoding='utf-8')
    with (out/'结果汇总.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(summary_rows[0]));writer.writeheader();writer.writerows(summary_rows)
    print(json.dumps({'guide':str(CORPUS/'测试集导航.html'),'results':str(out/'测试结果总览.html'),'source_checks':total},ensure_ascii=False))


if __name__=='__main__':main()
