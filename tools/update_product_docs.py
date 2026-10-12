"""Update product Word documents using the retained V2.3 blueprint's OOXML.

Unchanged ZIP parts (styles, numbering, relationships and page furniture) are
copied byte-for-byte. Original files are never overwritten. No research data
or credentials are read. Run with the bundled document-authoring Python.
"""
import copy
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / 'docs' / 'product'
REFERENCE = PRODUCT / '02_论文科研数据异常筛查Agent建设蓝图_V2.3.docx'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
NS = {'w': W[1:-1]}
QA = ROOT / 'docs' / 'verification' / '2026-10-11-release' / 'documents'


def text(paragraph):
    return ''.join(paragraph.xpath('.//w:t/text()', namespaces=NS))


def replace_text(paragraph, value):
    # Keep every original run/property; distribute replacements without losing
    # label emphasis when the label itself has not changed.
    nodes = paragraph.xpath('.//w:t', namespaces=NS)
    if not nodes:
        run = ET.SubElement(paragraph, W + 'r')
        nodes = [ET.SubElement(run, W + 't')]
    first = nodes[0].text or ''
    if len(nodes) > 1 and value.startswith(first) and first:
        nodes[1].text = value[len(first):]
        for node in nodes[2:]:
            node.text = ''
    else:
        nodes[0].text = value
        for node in nodes[1:]:
            node.text = ''


def plain_clone(pattern, value):
    paragraph = copy.deepcopy(pattern)
    props = paragraph.find(W + 'pPr')
    run_props = paragraph.find('w:r/w:rPr', NS)
    for child in list(paragraph):
        if child is not props:
            paragraph.remove(child)
    run = ET.SubElement(paragraph, W + 'r')
    if run_props is not None:
        run.append(copy.deepcopy(run_props))
    ET.SubElement(run, W + 't').text = value
    return paragraph


def save_from_reference(tree, output):
    xml = ET.tostring(tree, xml_declaration=True, encoding='UTF-8', standalone=True)
    with ZipFile(REFERENCE) as source, ZipFile(output, 'w') as target:
        for entry in source.infolist():
            target.writestr(entry, xml if entry.filename == 'word/document.xml'
                            else source.read(entry.filename))
    with ZipFile(REFERENCE) as source, ZipFile(output) as final:
        preserved = [name for name in source.namelist() if name != 'word/document.xml']
        assert all(source.read(name) == final.read(name) for name in preserved)
    return {'file': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'preserved_package_parts': len(preserved), 'changed_parts': ['word/document.xml']}


def main():
    QA.mkdir(parents=True, exist_ok=True)
    original_hash = hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
    with ZipFile(REFERENCE) as archive:
        tree = ET.fromstring(archive.read('word/document.xml'))
    body = tree.find(W + 'body')
    paragraphs = list(body.findall(W + 'p'))
    replacements = {
        'V2.3｜': 'V2.4｜本地交付版｜2026 年 10 月 11 日',
        '回原表核对：': '回原表核对：确认单位、公式和原始记录；可选逐条 AI 解释，也可提交参考版本并明确匹配方式核对数值差异。',
        '报告区：': '报告区：初筛 HTML、JSON 和原始记录可下载；人工复核、已保存 AI 解释及参考版本核对随新冻结的四格式报告保存，旧报告不改写。',
        '每项结果至少输出：': '每项结果至少输出：优先级、问题类型、文件、数据表、真实行列、关系式、命中数量及完整原始数值。编号等机械序列不冒充测量异常，原引擎记录保留。',
        '接口：': '接口：健康检查、任务扫描、公开材料候选、复核与报告、逐条解释报价和执行、参考表预览和比较、JSON及原始记录下载。',
        '本版范围：': '本版范围：本地上传、真实数值扫描、读取范围、人工复核、逐条 AI 解释、参考版本核对、历史记录及四格式报告。',
        'PDF、Word 的实际': 'PDF、Word 的实际读取程度取决于源文件结构。分别说明文字可读但数值表未读、扫描图片或加密限制；不做 OCR 或解密，不把置信区间等复合文字误作单个原始观测。',
    }
    matched = set()
    for paragraph in paragraphs:
        current = text(paragraph)
        for prefix, value in replacements.items():
            if current.startswith(prefix):
                replace_text(paragraph, value)
                matched.add(prefix)
    assert matched == set(replacements), 'Retained blueprint slots changed'
    plain = next(p for p in paragraphs if text(p).startswith('主页面包含'))
    additions = {
        '报告区：': '版本核对区：原表和参考表明确选择工作表、列对应及唯一编号；无编号时须确认相同数据顺序。列出双方位置和完整原值，不自动判断哪一版正确。',
        '数字与统计信号：': '参考版本差异：独立于统计扫描进行确定性比较，可定位孤立录入差异。重复或空白编号拒绝，未匹配行和截断范围标明；参考表也可能有误。',
        '运行产物：': '版本核对范围：CSV、TSV、XLSX、XLSM；单份20 MB，每轮20份/100 MB，最多20万单元格。页面和文字报告每组前100处，JSON及Excel最多保留5000处；公式无缓存不比较，不执行宏。',
        '异常是待复核统计信号，不能': '上传上限不等于已验证处理能力；引擎内存和时限为1 GiB及180秒，密集100 MB材料未验收。模型领域准确性、实际账单、Docker及平台运行仍待验收。',
        '后端自动测试、真实 HTTP': '当前修复验收记录：210项自动回归，12案页面流程及12案原值核对，8案Mock解释及1次失败隔离，2案公开勘误参考核对，10条旧真实回复当前导出，共255项通过。Mock不算模型效果，旧回复不算新增调用；最终仍需用户及领域人员人工验收。',
    }
    for prefix, value in additions.items():
        anchor = next(p for p in body.findall(W + 'p') if text(p).startswith(prefix))
        anchor.addnext(plain_clone(plain, value))
    records = [save_from_reference(tree, PRODUCT / '02_论文科研数据异常筛查Agent建设蓝图_V2.4.docx')]

    # Tutorial content has one Markdown authority. Reuse the blueprint's page
    # system and paragraph roles rather than introducing a second visual style.
    with ZipFile(REFERENCE) as archive:
        tutorial = ET.fromstring(archive.read('word/document.xml'))
    tutorial_body = tutorial.find(W + 'body')
    title_pattern = paragraphs[0]
    heading_pattern = next(p for p in paragraphs if text(p) == '一、项目定位')
    for child in list(tutorial_body):
        if child.tag != W + 'sectPr':
            tutorial_body.remove(child)
    for line in (PRODUCT / '03_使用教程.md').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        value = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line).replace('`', '')
        if line.startswith('# '):
            paragraph = plain_clone(title_pattern, '论文科研数据异常筛查使用教程')
        elif line.startswith('## '):
            paragraph = plain_clone(heading_pattern, value[3:])
            if value[3:] == '交付包运行':
                ET.SubElement(paragraph.find(W + 'pPr'), W + 'pageBreakBefore')
        else:
            paragraph = plain_clone(plain, value)
            ET.SubElement(paragraph.find(W + 'pPr'), W + 'keepLines')
        tutorial_body.insert(len(tutorial_body) - 1, paragraph)
    records.append(save_from_reference(tutorial, PRODUCT / '03_使用教程_V2.4.docx'))
    assert hashlib.sha256(REFERENCE.read_bytes()).hexdigest() == original_hash
    (QA / 'template-fidelity.json').write_text(json.dumps({
        'reference': str(REFERENCE), 'reference_sha256': original_hash,
        'preserved': ['styles', 'numbering', 'relationships', 'section geometry'],
        'outputs': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(records, ensure_ascii=False))


if __name__ == '__main__':
    main()
