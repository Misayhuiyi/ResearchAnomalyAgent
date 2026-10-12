"""Download public snapshots for LOCAL tests. No model call, no overwrite.

Original papers/data stay git-ignored. Generated cases are explicitly labelled.
Run with the product Python (openpyxl is needed for the correction comparison).
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import shutil
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'test-corpus'
MAX_DOWNLOAD = 20 * 1024 * 1024


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target.read_bytes()
    request = urllib.request.Request(url, headers={'User-Agent': 'PaperAudit-local-verification/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError('Public material exceeds the bounded download size.')
    if target.suffix == '.pdf' and not data.startswith(b'%PDF'):
        raise ValueError('Publisher returned a page instead of a PDF.')
    if target.suffix in {'.zip', '.xlsx'} and not data.startswith(b'PK'):
        raise ValueError('Publisher returned a page instead of an archive/workbook.')
    target.write_bytes(data)
    return data


def plos(doi, journal, name):
    page = f'https://journals.plos.org/{journal}/article?id={doi}'
    folder = CORPUS / 'originals' / name
    raw = fetch(page, folder / 'publisher.html').decode('utf-8')
    fetch(f'https://journals.plos.org/{journal}/article/file?id={doi}&type=printable', folder / f'{name}.pdf')
    links = re.findall(r'href="([^"]*article/asset[^"]*)"', raw)
    for link in dict.fromkeys(links):
        link = html.unescape(link)
        if '.s00' in link:
            print(name, 'SUPPLEMENT', link, flush=True)
    return folder, links


def download_sources():
    CORPUS.mkdir(exist_ok=True)
    for doi, journal, name in [
        ('10.1371/journal.pone.0266012', 'plosone', 'Sousa2022'),
        ('10.1371/journal.pone.0356340', 'plosone', 'Sousa2026Correction'),
        ('10.1371/journal.pgen.1008835', 'plosgenetics', 'Jin2020'),
        ('10.1371/journal.pgen.1010199', 'plosgenetics', 'Jin2022Correction'),
    ]:
        plos(doi, journal, name)
    page = 'https://www.research.autodesk.com/publications/same-stats-different-graphs/'
    raw = fetch(page, CORPUS/'originals/Datasaurus2017/publisher.html').decode('utf-8')
    print('DATASAURUS DOWNLOAD LINKS', re.findall(r'href="([^"]*(?:\.csv|\.tsv|\.zip|\.pdf)[^"]*)"', raw), flush=True)
    fetch('https://www.research.autodesk.com/app/uploads/2023/03/same-stats-different-graphs.pdf_rec2hRjLLGgM7Cn2T.pdf', CORPUS/'originals/Datasaurus2017/Datasaurus2017.pdf')
    target=CORPUS/'originals/Fisher1936/Fisher1936.pdf'
    if not target.exists():
        for url in [
            'https://digital.library.adelaide.edu.au/server/api/core/bitstreams/1801cd68-028a-4380-a9c6-30ca9b0aa0d3/content',
            'https://digital.library.adelaide.edu.au/dspace/bitstream/2440/15227/1/138.pdf',
            'https://digital.library.adelaide.edu.au/bitstream/2440/15227/1/138.pdf',
        ]:
            try:
                fetch(url,target)
                save_json(target.parent/'download.json',{'url':url})
                break
            except (urllib.error.HTTPError,ValueError):
                continue
        if not target.exists():
            raise ValueError('The scholarly repository PDF is currently unavailable.')
    fetch('https://archive.ics.uci.edu/static/public/53/iris.zip', CORPUS/'originals/Fisher1936/iris.zip')
    fetch('https://raw.githubusercontent.com/jumpingrivers/datasauRus/main/inst/extdata/DatasaurusDozen-Long.tsv', CORPUS/'originals/Datasaurus2017/DatasaurusDozen-Long.tsv')
    fetch('https://raw.githubusercontent.com/jumpingrivers/datasauRus/main/LICENSE', CORPUS/'originals/Datasaurus2017/LICENSE')
    for journal,doi,number,target in [
        ('plosone','10.1371/journal.pone.0266012',1,'Sousa2022/original.xlsx'),
        ('plosone','10.1371/journal.pone.0356340',1,'Sousa2026Correction/corrected.xlsx'),
        ('plosgenetics','10.1371/journal.pgen.1010199',3,'Jin2022Correction/corrected.csv'),
        ('plosgenetics','10.1371/journal.pgen.1008835',7,'Jin2020/original.xlsx'),
        ('plosgenetics','10.1371/journal.pgen.1008835',8,'Jin2020/figures-original.xlsx'),
        ('plosgenetics','10.1371/journal.pgen.1010199',4,'Jin2022Correction/figures-corrected.xlsx'),
    ]:
        fetch(f'https://journals.plos.org/{journal}/article/file?type=supplementary&id={doi}.s{number:03}', CORPUS/'originals'/target)


def write_table(path, headers, rows):
    if path.suffix=='.xlsx':
        from openpyxl import Workbook
        book=Workbook(); sheet=book.active; sheet.title='测试数据'
        sheet.append(headers)
        for row in rows: sheet.append(row)
        book.save(path);book.close()
    else:
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.writer(handle,delimiter='\t' if path.suffix=='.tsv' else ',')
            writer.writerow(headers);writer.writerows(rows)


def build_cases():
    if (CORPUS/'manifest.json').exists():
        print('Existing immutable corpus retained; use it without regeneration.',flush=True)
        return
    originals=CORPUS/'originals'
    peng=originals/'Gorman2014';peng.mkdir(exist_ok=True)
    for name in ('Gorman2014.pdf','penguins_raw.csv'):
        old=ROOT/'docs/verification/2026-09-30-real-paper/materials'/name
        if old.exists(): shutil.copy2(old,peng/name)
        else:
            url=(f'https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0090081&type=printable'
                 if name.endswith('.pdf') else 'https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins_raw.csv')
            fetch(url,peng/name)
    with zipfile.ZipFile(originals/'Fisher1936/iris.zip') as archive:
        raw=archive.read('iris.data').decode('utf-8')
        (originals/'Fisher1936/iris.names').write_bytes(archive.read('iris.names'))
    iris=[row for row in csv.reader(io.StringIO(raw)) if row]
    assert len(iris)==150
    assert iris[34][:4]==['4.9','3.1','1.5','0.1']
    assert iris[37][:4]==['4.9','3.1','1.5','0.1']
    fixed=[row[:] for row in iris];fixed[34][3]='0.2';fixed[37][1:3]=['3.6','1.4']
    headers=['sepal_length','sepal_width','petal_length','petal_width','species']
    write_table(originals/'Fisher1936/iris_uci.csv',headers,iris)
    write_table(originals/'Fisher1936/iris_corrected.csv',headers,fixed)
    with (peng/'penguins_raw.csv').open(encoding='utf-8-sig',newline='') as handle:
        peng_rows=list(csv.DictReader(handle))
    with (originals/'Datasaurus2017/DatasaurusDozen-Long.tsv').open(encoding='utf-8',newline='') as handle:
        dino=list(csv.DictReader(handle,delimiter='\t'))
    assert len(dino)==1846
    cases=[]
    def case(id,title,group,paper,files,expected,profile='review',notes=''):
        folder=CORPUS/'cases'/id;folder.mkdir(parents=True,exist_ok=True)
        uploads=[]
        for source in files:
            target=folder/source.name;shutil.copy2(source,target)
            uploads.append(str(target.relative_to(CORPUS)).replace('\\','/'))
        value={'id':id,'title':title,'group':group,'paper':paper,'profile':profile,
               'uploads':uploads,'expected':expected,'notes':notes}
        cases.append(value)
        save_json(folder/'预期与来源.json',value)
        return folder
    case('B01_企鹅原始数据','企鹅生态研究：未改动公开数据','baseline','Gorman2014',
         [peng/'Gorman2014.pdf',peng/'penguins_raw.csv'],{'data_rows':344},
         notes='未人为改动；不等于无错误认证。整数、测量精度或舍入提示需结合仪器解释。')
    case('B02_图形研究公开数据','同统计不同图形：作者设计数据','baseline','Datasaurus2017',
         [originals/'Datasaurus2017/Datasaurus2017.pdf',originals/'Datasaurus2017/DatasaurusDozen-Long.tsv'],
         {'data_rows':1846,'groups':13},notes='作者有意构造图形；同统计指标或结构规律不应直接判为错误。数据来自作者页面认可的维护包再发布版本。')
    case('B03_Iris按来源修正','Iris：按 UCI 勘误修正三个数值','corrected_reference','Fisher1936',
         [originals/'Fisher1936/Fisher1936.pdf',originals/'Fisher1936/iris_corrected.csv'],{'data_rows':150},
         notes='仅修正 UCI 指出的三处录入差异；不是独立认证的正常论文。历史 PDF 可能无法完整读出表格，无 OCR。')
    case('E01_Iris已知录入差异','Iris：UCI 明确记录的三处差异','documented_error','Fisher1936',
         [originals/'Fisher1936/Fisher1936.pdf',originals/'Fisher1936/iris_uci.csv'],
         {'data_rows':150,'known_cells':[{'file':'iris_uci.csv','row':36,'column':4,'original':'0.1','corrected':'0.2'},
                                      {'file':'iris_uci.csv','row':39,'column':2,'original':'3.1','corrected':'3.6'},
                                      {'file':'iris_uci.csv','row':39,'column':3,'original':'1.5','corrected':'1.4'}]},
         notes='样本序号35/38加表头对应文件行36/39。录入差异属于流传数据版本，不据此指控 Fisher 原论文。一般孤立录入错误不保证能被关系扫描命中。')
    case('E02_运动实验录入错误','运动实验：公开勘误前数据','documented_error','Sousa2022',
         [originals/'Sousa2022/Sousa2022.pdf',originals/'Sousa2022/original.xlsx'],
         {'known_cells':[{'file':'original.xlsx','sheet':'Experiment 2','row':6,'column':11,
                          'original':65.95549826312603,'corrected':68.88}]},
         notes='2026勘误明确指出第4位参与者 VO2maxVB 录入错误。原版 K5/K6 相同不是不端证据，孤立录入错可能漏检。')
    case('B04_运动实验修正版','运动实验：出版社修正版本','corrected_reference','Sousa2022',
         [originals/'Sousa2022/Sousa2022.pdf',originals/'Sousa2026Correction/Sousa2026Correction.pdf',originals/'Sousa2026Correction/corrected.xlsx'],
         {'corrected_cells':[{'file':'corrected.xlsx','sheet':'Experiment 2','row':6,'column':11,'value':68.88}]})
    case('E03_果蝇校正错误','果蝇代谢研究：勘误前图表数据','documented_error','Jin2020',
         [originals/'Jin2020/Jin2020.pdf',originals/'Jin2020/figures-original.xlsx'],
         {'known_error_sheet':'Data_for_S2'},profile='triage',
         notes='勘误指出批次校正只作用于AL而遗漏DR；默认测试完整 S2 图表数据，完整 S1 代谢矩阵额外留在 originals。需要重现分析才能判断，不能只凭关系线索确证。')
    case('B05_果蝇修正图表数据','果蝇代谢研究：出版社修正图表数据','corrected_reference','Jin2020',
         [originals/'Jin2020/Jin2020.pdf',originals/'Jin2022Correction/Jin2022Correction.pdf',originals/'Jin2022Correction/figures-corrected.xlsx'],
         {'paired_case':'E03_果蝇校正错误'},profile='triage')
    # Positive controls use real values but ALL transformed columns are invented tests.
    bases=[float(r['Culmen Length (mm)']) for r in peng_rows if r['Culmen Length (mm)'] not in ('NA','')][:35]
    values=[[x,round(x+.3,8)] for x in bases]
    folder=case('C01_人工固定平移','企鹅数据派生：人工固定平移','injected','Gorman2014',[peng/'Gorman2014.pdf'],
                {'relations':[{'kind':'constant_offset','n':35,'parameter':'offset','value':.3}]},
                notes='人工生成第二列，非原论文错误；35行 treated=control+0.3。')
    write_table(folder/'人工固定平移.csv',['control','treated'],values)
    cases[-1]['uploads'].append(str((folder/'人工固定平移.csv').relative_to(CORPUS)).replace('\\','/'))
    bases=[float(r[0]) for r in iris[:35]]
    folder=case('C02_人工固定比例','Iris 数据派生：人工固定比例','injected','Fisher1936',[originals/'Fisher1936/Fisher1936.pdf'],
                {'relations':[{'kind':'constant_ratio','n':35,'parameter':'ratio','value':2}]},
                notes='人工生成第二列，非原论文错误；35行 scaled=control×2。')
    write_table(folder/'人工固定比例.xlsx',['control','scaled'],[[x,round(x*2,8)] for x in bases])
    cases[-1]['uploads'].append(str((folder/'人工固定比例.xlsx').relative_to(CORPUS)).replace('\\','/'))
    bases=[float(r['x']) for r in dino[:35]]
    folder=case('C03_人工线性与重复','图形数据派生：人工线性及重复','injected','Datasaurus2017',[originals/'Datasaurus2017/Datasaurus2017.pdf'],
                {'relations':[{'kind':'exact_linear','n':35,'parameter':'slope','value':1.5},
                              {'kind':'identical_column','n':35}]},profile='forensic',
                notes='人工生成 transformed=1.5×control+0.7；copied=control。保留全精度，非原论文问题。')
    write_table(folder/'人工线性与重复.tsv',['control','transformed','copied'],[[x,x*1.5+.7,x] for x in bases])
    cases[-1]['uploads'].append(str((folder/'人工线性与重复.tsv').relative_to(CORPUS)).replace('\\','/'))
    folder=case('C04_人工舍入聚集','企鹅数据派生：人工舍入聚集','injected','Gorman2014',[peng/'Gorman2014.pdf'],
                {'rounding':{'n':4,'rounded_to':.5,'originals':[.451,.469,.531,.459]}},
                notes='人工测试列；前四个值按1位小数比较均为0.5，页面应显示0.451/0.469/0.531/0.459及行2–5；原论文无该列。')
    write_table(folder/'人工舍入聚集.csv',['control','rounding_test'],[[bases[i],x] for i,x in enumerate([.451,.469,.531,.459]+[2+i*.27 for i in range(31)])])
    cases[-1]['uploads'].append(str((folder/'人工舍入聚集.csv').relative_to(CORPUS)).replace('\\','/'))
    # Freeze publisher differences BEFORE executing the candidate scanner.
    from openpyxl import load_workbook
    diffs=[]
    for left,right in [('Sousa2022/original.xlsx','Sousa2026Correction/corrected.xlsx'),
                       ('Jin2020/figures-original.xlsx','Jin2022Correction/figures-corrected.xlsx')]:
        a=load_workbook(originals/left,read_only=True,data_only=True);b=load_workbook(originals/right,read_only=True,data_only=True)
        for sa in a:
            sb=b[sa.title]
            for row, (ra,rb) in enumerate(zip(sa.values,sb.values),1):
                for col,(va,vb) in enumerate(zip(ra,rb),1):
                    if va!=vb: diffs.append({'original_file':left,'corrected_file':right,'sheet':sa.title,'row':row,'column':col,'before':va,'after':vb})
        a.close();b.close()
    save_json(CORPUS/'publisher-differences.json',diffs)
    for item in cases: save_json(CORPUS/'cases'/item['id']/'预期与来源.json',item)
    hashes={str(p.relative_to(CORPUS)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in CORPUS.rglob('*') if p.is_file()}
    manifest={'version':'public-paper-corpus-1','created_at':datetime.now(timezone.utc).isoformat(),
              'purpose':'公开开发回归集及人工工具练习，不是盲测或研究诚信结论',
              'papers':[
                  {'id':'Gorman2014','doi':'10.1371/journal.pone.0090081','source':'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0090081','data':'https://github.com/allisonhorst/palmerpenguins/blob/main/inst/extdata/penguins_raw.csv','license':'paper CC BY; republished data CC0'},
                  {'id':'Fisher1936','doi':'10.1111/j.1469-1809.1936.tb02137.x','source':'https://digital.library.adelaide.edu.au/items/d26c5e1c-2751-472f-9738-9db69dc216f7','data':'https://archive.ics.uci.edu/dataset/53/iris','license':'paper permission-granted scholarly repository copy, LOCAL ONLY; UCI data CC BY 4.0'},
                  {'id':'Datasaurus2017','doi':'10.1145/3025453.3025912','source':'https://www.research.autodesk.com/publications/same-stats-different-graphs/','data':'https://github.com/jumpingrivers/datasauRus/blob/main/inst/extdata/DatasaurusDozen-Long.tsv','license':'author-hosted paper LOCAL ONLY; package data license metadata retained, no redistribution'},
                  {'id':'Sousa2022','doi':'10.1371/journal.pone.0266012','source':'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0266012','correction':'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0356340','license':'CC BY'},
                  {'id':'Jin2020','doi':'10.1371/journal.pgen.1008835','source':'https://journals.plos.org/plosgenetics/article?id=10.1371/journal.pgen.1008835','correction':'https://journals.plos.org/plosgenetics/article?id=10.1371/journal.pgen.1010199','license':'CC BY'},
              ],'hashes':hashes,'cases':cases,'paid_calls_authorized':0,
              'criteria':{'source_values':'zero mismatched addressed evidence cells','positive_controls':'expected relation, parameter, count all match',
                          'workflow':'upload, job, evidence, neutral review, JSON/raw, four report downloads, history',
                          'baseline':'no no-error certificate; do not require zero statistical signals',
                          'documented_error':'record whether exact known cell is highlighted; misses remain reported',
                          'ai':'mock software flow separately labelled; real calls require new fee approval'}}
    save_json(CORPUS/'manifest.json',manifest)
    save_json(ROOT/'tools/paper_corpus_manifest.json',manifest)
    print(json.dumps({'cases':len(cases),'papers':5,'publisher_differences':len(diffs)},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    download_sources()
    build_cases()
