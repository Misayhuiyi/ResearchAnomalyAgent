"""Explicit version comparison. Differences are not error or misconduct labels."""
from __future__ import annotations
import hashlib
import json
import re
import threading
import uuid
from decimal import Decimal,InvalidOperation
from pathlib import Path
from review_store import ReviewStore,ReviewError,Conflict,Unavailable,digest,encode,now
from table_sources import read_tables,FORMATS

LOCK=threading.RLock()
BOUNDARY='这里只说明两个版本的数值不同，不能据此判断哪一版正确，也不能认定科研不端或作者意图。'
MAX_DIFFERENCES=5000

def safe_name(value):
    if (not isinstance(value,str) or not value or len(value)>180 or Path(value).name!=value or
        any(c in '<>:"/\\|?*' or ord(c)<32 for c in value) or value.endswith(('.', ' ')) or
        re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])',Path(value).stem)):
        raise ReviewError('文件名不合法。')
    if Path(value).suffix.lower() not in FORMATS:raise ReviewError('版本核对支持 CSV、TSV、XLSX 和 XLSM。')
    return value

def canonical(value):
    text=str(value if value is not None else '').strip()
    if text:
        try:
            number=Decimal(text)
            if number.is_finite():return ('number',number)
        except InvalidOperation:pass
    return ('text',text)

def data_rows(table):return [r for r in table['rows'] if r['row_idx']>table['header_row'] and any(v is not None and str(v).strip() for v in r['values'])]
def value(row,index):return row['values'][index] if index<len(row['values']) else None
def describe(tables):
    return [{'sheet':name,'header_row':t['header_row'],'rows':len(data_rows(t)),
             'columns':[{'index':i,'label':label} for i,label in enumerate(t['headers'])]} for name,t in tables.items()]

class ReferenceComparisonService:
    def __init__(self,root):
        self.root=Path(root);self.store=ReviewStore(root)
        with self.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS reference_inputs(id TEXT PRIMARY KEY,scan TEXT,tenant TEXT,owner TEXT,body TEXT);
                CREATE TABLE IF NOT EXISTS reference_runs(id TEXT PRIMARY KEY,scan TEXT,tenant TEXT,owner TEXT,signature TEXT,body TEXT);''')

    def _source(self,actor,scan):
        if not isinstance(scan,str) or not re.fullmatch('[a-f0-9]{12}',scan):raise Unavailable('检查记录不存在。')
        with self.store.connect() as db:
            row=self.store._scan(db,actor,scan)
            return row['source_hash'],json.loads(row['source'])

    def _read(self,path):
        try:return read_tables(path)
        except Exception:raise ReviewError('表格无法用于版本核对，请确认表头、容量和文件格式。') from None

    def _source_path(self,scan,name,result):
        name=safe_name(name);root=(self.root/scan/'input').resolve();path=(root/name).resolve()
        if not root.is_relative_to(self.root.resolve()) or path.parent!=root or not path.is_file():raise Unavailable('原始表格不存在，请从本次已上传材料选择。')
        if result.get('sources') and name not in result['sources']:raise Unavailable('文件不属于本次检查。')
        expected=next((m.get('sha256') for m in result.get('material_sources',[]) if m.get('filename')==name),None)
        if expected and hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise Conflict('原始材料校验未通过。')
        return path

    def upload(self,actor,scan,source_file,filename,payload):
        with LOCK:
            source_hash,result=self._source(actor,scan);source=self._source_path(scan,source_file,result);filename=safe_name(filename)
            if not isinstance(payload,bytes) or not 0<len(payload)<=20*1024*1024:raise ReviewError('参考文件为空或超过 20 MB。')
            with self.store.connect() as db:
                prior=[json.loads(r['body']) for r in db.execute('SELECT body FROM reference_inputs WHERE scan=? AND tenant=? AND owner=?',(scan,actor.tenant,actor.subject))]
            if len(prior)>=20 or sum(r.get('size',0) for r in prior)+len(payload)>100*1024*1024:
                raise ReviewError('本次参考文件达到 20 份或 100 MB 上限，请建立新的材料检查。')
            source_tables=self._read(source);reference_id=uuid.uuid4().hex
            folder=self.root/scan/'references'/reference_id;folder.mkdir(parents=True,exist_ok=False)
            path=folder/filename;path.write_bytes(payload)
            try:tables=self._read(path)
            except ReviewError:
                path.unlink();folder.rmdir();raise  # Own new rejected upload only.
            body={'reference_id':reference_id,'source_file':source_file,'filename':filename,'source_hash':source_hash,
                  'original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'reference_sha256':hashlib.sha256(payload).hexdigest(),'source_sheets':describe(source_tables),
                  'reference_sheets':describe(tables),'created_at':now(),'size':len(payload)}
            with self.store.connect() as db:
                db.execute('INSERT INTO reference_inputs VALUES(?,?,?,?,?)',(reference_id,scan,actor.tenant,actor.subject,encode(body)))
            return body

    def view(self,actor,scan,reference_id):
        self._source(actor,scan)
        if not isinstance(reference_id,str) or not re.fullmatch('[a-f0-9]{32}',reference_id):raise Unavailable('参考记录不存在。')
        with self.store.connect() as db:
            row=db.execute('SELECT body FROM reference_inputs WHERE id=? AND scan=? AND tenant=? AND owner=?',
                           (reference_id,scan,actor.tenant,actor.subject)).fetchone()
        if not row:raise Unavailable('参考记录不存在或无权查看。')
        return json.loads(row['body'])

    @staticmethod
    def _mapping(mapping,left,right,allow_empty=False):
        if not isinstance(mapping,list) or (not mapping and not allow_empty) or len(mapping)>200:raise ReviewError('请选择匹配列和核对列。')
        seen=set()
        for pair in mapping:
            if (not isinstance(pair,dict) or set(pair)!={'source','reference'} or any(type(pair[k]) is not int for k in pair) or
                not 0<=pair['source']<len(left['headers']) or not 0<=pair['reference']<len(right['headers']) or pair['source'] in seen):
                raise ReviewError('列对应关系无效或重复，请重新选择。')
            seen.add(pair['source'])
        if len({p['reference'] for p in mapping})!=len(mapping):raise ReviewError('参考列不能重复匹配。')

    def compare(self,actor,scan,reference_id,source_sheet,reference_sheet,keys,columns,confirm_order=False):
        with LOCK:
            source_hash,result=self._source(actor,scan);meta=self.view(actor,scan,reference_id)
            if meta['source_hash']!=source_hash:raise Conflict('材料版本已变化，请重新选择参考文件。')
            source=self._source_path(scan,meta['source_file'],result);reference=self.root/scan/'references'/reference_id/meta['filename']
            original_sha=meta.get('original_sha256') or next((m.get('sha256') for m in result.get('material_sources',[]) if m.get('filename')==meta['source_file']),None)
            if not original_sha:raise ReviewError('旧参考记录缺少原表校验，请重新读取参考文件。')
            if hashlib.sha256(source.read_bytes()).hexdigest()!=original_sha:raise Conflict('原始表格已变化，请建立新的材料版本后核对。')
            if not reference.resolve().is_relative_to((self.root/scan/'references').resolve()):raise Conflict('参考材料路径无效。')
            if hashlib.sha256(reference.read_bytes()).hexdigest()!=meta['reference_sha256']:raise Conflict('参考材料校验未通过。')
            left=self._read(source);right=self._read(reference)
            if not isinstance(source_sheet,str) or not isinstance(reference_sheet,str) or source_sheet not in left or reference_sheet not in right:raise ReviewError('请选择存在的工作表。')
            left,right=left[source_sheet],right[reference_sheet]
            self._mapping(keys,left,right,True);self._mapping(columns,left,right)
            if not keys and confirm_order is not True:raise ReviewError('没有匹配编号时，请明确确认两个版本的数据顺序一致。')
            if any(p['source'] in {k['source'] for k in keys} or p['reference'] in {k['reference'] for k in keys} for p in columns):raise ReviewError('匹配编号不应同时作为核对数值，请另选核对列。')
            signature=digest([source_hash,reference_id,source_sheet,reference_sheet,keys,columns,confirm_order])
            with self.store.connect() as db:
                prior=db.execute('SELECT body FROM reference_runs WHERE scan=? AND tenant=? AND owner=? AND signature=?',
                                 (scan,actor.tenant,actor.subject,signature)).fetchone()
            if prior:return json.loads(prior['body'])
            a,b=data_rows(left),data_rows(right);pairs=[];missing=[]
            if keys:
                def index(rows,side):
                    indexed={}
                    for row in rows:
                        key=tuple(canonical(value(row,p[side])) for p in keys)
                        if any(k==('text','') for k in key):raise ReviewError('匹配编号存在空值，无法安全对应，请修正或选择其他匹配列。')
                        if key in indexed:raise ReviewError('匹配编号重复，无法唯一对应；请增加匹配列或改用已确认的数据顺序。')
                        indexed[key]=row
                    return indexed
                aa,bb=index(a,'source'),index(b,'reference')
                for key,row in aa.items():
                    if key in bb:pairs.append((row,bb[key]))
                    else:missing.append({'side':'source','row':row['row_idx']})
                missing.extend({'side':'reference','row':row['row_idx']} for key,row in bb.items() if key not in aa)
            else:
                if len(a)!=len(b):raise ReviewError('两个版本的数据行数不同，不能按顺序直接核对；请选择唯一匹配编号。')
                pairs=list(zip(a,b))
            differences=[];total=0
            for ra,rb in pairs:
                for pair in columns:
                    va,vb=value(ra,pair['source']),value(rb,pair['reference'])
                    if canonical(va)==canonical(vb):continue
                    total+=1
                    if len(differences)<MAX_DIFFERENCES:
                        differences.append({'source':{'file':meta['source_file'],'sheet':source_sheet,'row':ra['row_idx'],
                            'column':left['headers'][pair['source']],'column_idx':pair['source']+1,'value':va},
                            'reference':{'file':meta['filename'],'sheet':reference_sheet,'row':rb['row_idx'],
                            'column':right['headers'][pair['reference']],'column_idx':pair['reference']+1,'value':vb}})
            value_out={'comparison_id':uuid.uuid4().hex,'scan_id':scan,'source_hash':source_hash,'reference_id':reference_id,
                  'source_file':meta['source_file'],'reference_file':meta['filename'],'reference_sha256':meta['reference_sha256'],
                  'original_sha256':original_sha,
                  'source_sheet':source_sheet,'reference_sheet':reference_sheet,'keys':keys,'columns':columns,
                  'matching':'key' if keys else 'confirmed_order','matched_rows':len(pairs),'unmatched_rows':missing,
                  'differences_total':total,'differences':differences,'truncated':total>MAX_DIFFERENCES,
                  'status':'partial' if total>MAX_DIFFERENCES or missing else 'complete','boundary':BOUNDARY,'created_at':now()}
            value_out['comparison_hash']=digest(value_out)
            with self.store.connect() as db:
                db.execute('INSERT INTO reference_runs VALUES(?,?,?,?,?,?)',(value_out['comparison_id'],scan,actor.tenant,actor.subject,signature,encode(value_out)))
            return value_out

    def reports(self,actor,scan):
        source_hash,_=self._source(actor,scan)
        with self.store.connect() as db:
            rows=db.execute('SELECT body FROM reference_runs WHERE scan=? AND tenant=? AND owner=? ORDER BY rowid DESC LIMIT 20',(scan,actor.tenant,actor.subject)).fetchall()
        result=[json.loads(r['body']) for r in rows]
        if any(r['source_hash']!=source_hash or digest({k:v for k,v in r.items() if k!='comparison_hash'})!=r['comparison_hash'] for r in result):raise Conflict('版本核对记录校验未通过。')
        return result

    def report_context(self,actor,scan):
        source_hash,_=self._source(actor,scan);items=[];seen=set();total=0
        for row in self.reports(actor,scan):
            identity=row['source_file'],row['source_sheet']
            if identity in seen:continue
            seen.add(identity);total+=len(row['differences'])
            if total>MAX_DIFFERENCES:raise ReviewError('报告版本差异超过 5000 处，请拆分材料后生成报告。')
            items.append(row)
        return {'scan_id':scan,'source_hash':source_hash,'items':items}
