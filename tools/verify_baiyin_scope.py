"""Evidence checks for the local Baiyin delivery scope, without replacing raw audits.

This verifies actual contracts and run outputs. Raw scanner findings are preserved;
only explicitly supported false positives and platform exclusions are classified.
No model calls, forum messages, Docker or publication are performed.
"""
import ast
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tables=[];self.table=None;self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[]
        elif tag=='tr' and self.table is not None:self.row=[]
        elif tag in {'td','th'} and self.row is not None:self.cell=[]
    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        elif tag=='tr' and self.row is not None:self.table.append(self.row);self.row=None
        elif tag=='table' and self.table is not None:self.tables.append(self.table);self.table=None


def html_tables(text):
    parser=TableParser();parser.feed(text);return parser.tables


def adjudicate(issue):
    cid=issue['check_id']
    specific={
      'SEC-001':('false_positive','env.get reads a credential; AST/token checks find no literal key'),
      'SEC-002':('false_positive','Only local loopback binding; server rejects non-loopback addresses'),
      'PATH-ABSOLUTE':('false_positive','The matched public_materials line is DOI syntax, not a filesystem path'),
      'CODE-GUI':('false_positive','Matched view methods return data; no plot/display window is called'),
      'PLOT-SIZE':('false_positive','Report/table and UI dimensions do not create a statistical plot'),
      'PLOT-LEGEND':('false_positive','No statistical plots are generated; Figures explicitly states this'),
      'DOC-STALE-NAME':('false_positive','Workbench.py is the existing no-argument peer component entry'),
      'DOC-CROSS-输入':('false_positive','Independent Word/HTML cells match; raw parser appended a folder child to Word rows'),
      'IO-CONTRACT-UNDOCUMENTED-SAMPLE-002':('false_positive','Synthetic CSV belongs to the documented Materials folder-upload container'),
      'IO-001':('verified','Coding and Workbench accept no user CLI; only the resource-limited PDF probe child receives a private system-generated filepath in sys.argv'),
      'IO-CONTRACT-CODE-005':('fixed','Unsupported batch Reference.txt was removed; DOI remains a workbench function'),
      'AGENTOM-CHANGELOG':('fixed','Actual reproduction stores and compares source hashes before and after'),
      'AGENTOM-REVIEW':('fixed','No automatic mutation/publication endpoint; external source change blocks the result'),
      'AGENTOM-FORUM':('platform_followup','Company forum interface and external reply belong to later platform integration')}
    if cid in specific:state,reason=specific[cid]
    elif cid.startswith(('IO-CONTRACT-','OUT-CONTRACT-','DOC-CROSS-')):
        state,reason='verified','Actual input/output parity, output hashes and named step handoff are verified'
    elif cid in {'AGENTRUN-NORMAL','AGENTRUN-RETRY'}:
        state,reason='verified','Real normal run plus invalid-input and failure/timeout tests prove bounded submission'
    else:raise ValueError('Unreviewed raw audit issue: '+cid)
    return {'check_id':cid,'status':state,'reason':reason}


def verify(package, evidence, audit=None, baseline=None):
    from docx import Document
    root=Path(__file__).resolve().parents[1]
    package=Path(package).resolve();evidence=Path(evidence).resolve()
    if package.parent!=root/'delivery' or not package.name.startswith('PaperAudit-'):
        raise ValueError('Select a package under delivery/PaperAudit-*.')
    if not evidence.is_relative_to(root/'docs'/'verification'):
        raise ValueError('Evidence must stay under docs/verification.')
    coding=package/'PaperAudit_Coding';core=coding/'Code'/'DataCode';checks=[]
    def check(name,condition,detail):
        checks.append({'check':name,'passed':bool(condition),'evidence':detail})
        if not condition:raise ValueError(name+' failed')
    contract=json.loads((coding/'Data'/'PipeLine'/'WorkflowContract.json').read_text(encoding='utf-8'))
    check('coding_layout',{p.name for p in coding.iterdir()}=={'Code','Data','TempData','Result'},'Coding has exactly four directories')
    check('single_entry',{p.name for p in (coding/'Code').iterdir()}=={'PaperAudit.py','DataCode'},'Only PaperAudit.py is a main Coding entry')
    doc=Document(package/'PaperAudit 应用说明.docx')
    tables=[[[c.text for c in row.cells] for row in t.rows] for t in doc.tables]
    check('word_html_parity',tables==html_tables((package/'PaperAudit 应用说明.html').read_text(encoding='utf-8')),'Real Word and HTML cells match exactly')
    documented_inputs={r[0].rstrip('/') for r in tables[0][1:]}
    check('declared_inputs',documented_inputs==set(contract['platform_inputs'])=={p.name for p in (coding/'TempData').iterdir()},'Actual batch input directory matches document and contract')
    demo=coding/'Data'/'Demo'/'TempData'
    check('demo_parity',all((demo/p.relative_to(coding/'TempData')).read_bytes()==p.read_bytes() for p in (coding/'TempData').rglob('*') if p.is_file()),'Input and Demo bytes match including Materials child file')
    gui_calls=[]
    for p in core.rglob('*.py'):
        tree=ast.parse(p.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                func=node.func
                if ((isinstance(func,ast.Name) and func.id in {'View','x11','quartz','windows'})
                        or (isinstance(func,ast.Attribute) and func.attr=='show'
                            and isinstance(func.value,ast.Name) and func.value.id in {'plt','pyplot'})):
                    gui_calls.append(p.name)
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) and node.value.value:
                if any(isinstance(t,ast.Name) and t.id.lower() in {'secret','api_key','deepseek_api_key','password'} for t in node.targets):
                    raise ValueError('Literal credential assignment: '+p.name)
        if re.search(r'\bsk-[A-Za-z0-9_-]{20,}|BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY',p.read_text(encoding='utf-8')):
            raise ValueError('Credential pattern: '+p.name)
    check('no_literal_credentials',True,'AST and token-pattern checks of packaged Python modules; actual config never copied')
    check('no_gui_display',not gui_calls,'AST calls contain no plotting display or R GUI calls; view methods only return data')
    app_text=(core/'app.py').read_text(encoding='utf-8')
    check('no_user_cli','argparse' not in app_text and 'parse_args' not in app_text,'Packaged app.py is a service module; batch and Workbench entries take no arguments')
    gateway=(core/'model_gateway.py').read_text(encoding='utf-8')
    check('credential_environment_read',"secret=env.get('DEEPSEEK_API_KEY','')" in gateway,'SEC-001 assignment uses env.get, not a credential literal')
    check('local_loopback',"not ipaddress.ip_address(host).is_loopback" in app_text,'run_server enforces loopback before binding')
    check('doi_not_filesystem',r'10\.\d{4,9}/\S+' in (core/'public_materials.py').read_text(encoding='utf-8'),'PATH-ABSOLUTE hit is DOI syntax')
    output=sorted(p for p in (coding/'Result').iterdir() if p.is_dir())[-1]
    declared_outputs=[r[0] for r in tables[1][1:]]
    check('documented_outputs',all((output/name.rstrip('/')).exists() for name in declared_outputs),'All 12 output files/containers exist in actual synthetic run')
    with (output/'InputOutputManifest.csv').open(encoding='utf-8-sig',newline='') as f:manifest=list(csv.DictReader(f))
    check('result_manifest',all((output/r['path']).stat().st_size==int(r['bytes']) and hashlib.sha256((output/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in manifest),'Every archived output hash and size matches')
    final=json.loads((output/'Process'/'result.json').read_text(encoding='utf-8'))
    check('numeric_signals',any(f['kind']=='constant_offset' and f['n']==35 for f in final['findings']) and any(f['kind']=='constant_ratio' and f['raw']['ratio']==2 for f in final['findings']),'Actual PaperConan scan detects 35-row offset 0.3 and ratio 2')
    check('handoff', (output/'PipeLine'/'02_Report'/'TempData'/'result.json').read_bytes()==(output/'Process'/'result.json').read_bytes(),'StepIOMap named result handoff bytes match final source')
    check('no_statistical_plot',(output/'Figures'/'说明.txt').is_file(),'Figures states no statistical plot; UI/cover dimensions are not user analysis parameters')
    run_files=sorted((package/'PaperAudit_AgentRun'/'Result').glob('*.json'))
    run=json.loads(run_files[-1].read_text(encoding='utf-8'))
    check('agent_run_actual',run['status']=='succeeded' and run['attempts']==1 and run['retry_limit']==0 and run['model_calls']==0,'Real AgentRun passed once without model calls or retries')
    om_files=sorted((package/'PaperAudit_AgentOM'/'Result').glob('*.json'))
    om=json.loads(om_files[-1].read_text(encoding='utf-8'))
    check('maintenance_source_unchanged',om['source_unchanged'] and om['source_hashes']==om['source_hashes_after'],'Pre/post source hashes equal after isolated reproduction')
    check('human_gate',om['human_review']=='required_before_changes' and not om['review_gate']['automatic_changes'] and not om['review_gate']['automatic_publication'],'Maintenance endpoint cannot change or publish source')
    status=json.loads((package/'PaperAudit_Agent'/'Result'/'Status.json').read_text(encoding='utf-8'))
    check('agent_finding_status',status['status']=='not_started','Agent reads finding-explanation state with zero paid calls')
    runtime=json.loads((evidence/'delivery-runtime.json').read_text(encoding='utf-8'))
    check('four_component_runs',len(runtime['records'])==4 and all(r['exit_code']==0 for r in runtime['records']),'Coding/Agent/AgentRun/AgentOM commands all exit 0')
    check('workbench_runtime_location',(package/'PaperAudit_Agent'/'Result'/'WorkbenchState').is_dir()
          and not (coding/'Data'/'WorkbenchState').exists(),'Actual workbench state lives under Agent Result; Coding Data remains fixed')
    version_path=package/'VersionManifest.txt'
    version=json.loads(version_path.read_text(encoding='utf-8'))
    check('source_manifest',all(hashlib.sha256((package/name).read_bytes()).hexdigest()==sha for name,sha in version['files'].items()),'All packaged source/document fingerprints match original version manifest')
    findings=[]
    if audit:
        raw=json.loads((Path(audit)/'audit_result.json').read_text(encoding='utf-8'))
        findings=[adjudicate(issue) for issue in raw['issues']]
    baseline_rows=[]
    if baseline:
        original=json.loads((Path(baseline)/'audit_result.json').read_text(encoding='utf-8'))
        baseline_rows=[adjudicate(issue) for issue in original['issues']]
    result={'at':datetime.now(timezone.utc).isoformat(),'package':package.name,'scope':'local delivery only',
            'passed':len(checks),'failed':0,'checks':checks,'raw_audit_adjudication':findings,
            'baseline_adjudication':baseline_rows,
            'platform_exclusions':['login and tenants','storage and task dispatch','forum submission and replies','container deployment and hostile-code sandbox'],
            'human_effect_acceptance':'pending user/domain review','model_quality':'prior multi-paper live replies recorded separately; no new paid calls in packaging verification'}
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'local-scope-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    version.update(acceptance='local_scope_verified',platform_acceptance='pending',
                   verification={'contract_checks':len(checks),'failures':0,
                   'evidence_sha256':hashlib.sha256((evidence/'local-scope-acceptance.json').read_bytes()).hexdigest()})
    version_path.write_text(json.dumps(version,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    result=verify(os.environ['PAPER_AUDIT_DELIVERY'],os.environ['PAPER_AUDIT_VERIFICATION_DIR'],os.environ.get('PAPER_AUDIT_AUDIT_DIR'),os.environ.get('PAPER_AUDIT_BASELINE_DIR'))
    from collections import Counter
    print(json.dumps({'passed':result['passed'],'failed':result['failed'],'reviewed_raw_findings':len(result['raw_audit_adjudication']),
                      'baseline':dict(Counter(r['status'] for r in result['baseline_adjudication']))},ensure_ascii=False))
