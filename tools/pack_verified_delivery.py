"""Create a clean local ZIP of an explicitly selected verified candidate.

No repository mutations/publication, no provider calls and no file deletions.
Runtime databases, workbench state, component reproduction copies and caches
are excluded. Only the Coding synthetic example Result is retained, as required
by the Baiyin sample-output contract; it is never committed to GitHub.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT=Path(__file__).resolve().parents[1]


def include(path):
    parts=path.parts
    if any(x in {'__pycache__','WorkbenchState','runtime','.venv','test-corpus','test-results'} for x in parts):
        return False
    if path.suffix.lower() in {'.pyc','.sqlite3','.tmp','.log'} or path.name.startswith('.env'):
        return False
    if parts[0] in {'PaperAudit_Agent','PaperAudit_AgentRun','PaperAudit_AgentOM'} and len(parts)>2 and parts[1]=='Result':
        return False
    if 'PipeLine' in parts and parts[0]=='PaperAudit_Coding' and 'Data' in parts:
        # Immutable workflow contract remains; runtime step handoffs are private.
        if any(x in {'TempData','Result'} for x in parts) and len(parts)>5:
            return False
    return True


def main():
    package=Path(os.environ['PAPER_AUDIT_DELIVERY']).resolve()
    evidence=Path(os.environ['PAPER_AUDIT_VERIFICATION_DIR']).resolve()
    if package.parent!=ROOT/'delivery' or not package.name.startswith('PaperAudit-'):
        raise ValueError('Select a local delivery candidate')
    if not evidence.is_relative_to(ROOT/'docs'/'verification'):
        raise ValueError('Select a local verification directory')
    acceptance=json.loads((evidence/'local-scope-acceptance.json').read_text(encoding='utf-8'))
    if acceptance['package']!=package.name or acceptance['failed'] or acceptance['passed']!=23:
        raise ValueError('Candidate contract verification missing')
    for name in ['browser-final/browser.json','additions-browser.json']:
        record=json.loads((evidence/name).read_text(encoding='utf-8'))
        if record.get('failed',0) or not record.get('passed'):
            raise ValueError('Candidate browser verification missing')
    manifest_path=package/'VersionManifest.txt'
    version=json.loads(manifest_path.read_text(encoding='utf-8'))
    for name,digest in version['files'].items():
        if hashlib.sha256((package/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Verified candidate source changed: '+name)
    # Refresh only publishable product descriptions, never runtime evidence.
    docs=package/'PaperAudit_Coding'/'Data'/'ProductDocs'
    for source in (ROOT/'docs'/'product').glob('*.md'):
        shutil.copy2(source,docs/source.name)
    for source in (ROOT/'docs'/'product').glob('*V2.4.docx'):
        shutil.copy2(source,docs/source.name)
    selected=[p for p in package.rglob('*') if include(p.relative_to(package))]
    version['files']={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in selected if p.is_file() and p!=manifest_path}
    version.update(product_version='2.4',distribution='local only; no credentials or real papers',
                   runtime_exclusions=['WorkbenchState','component reproduction Results','step handoffs','caches'],
                   browser_checks=43,ai_mock_checks=4,additional_flow_checks=4)
    manifest_path.write_text(json.dumps(version,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=package.with_suffix('.zip')
    if archive.exists():raise ValueError('Never overwrite an earlier ZIP')
    with ZipFile(archive,'w',ZIP_DEFLATED) as output:
        for p in selected:
            output.write(p,(Path(package.name)/p.relative_to(package)).as_posix())
    with ZipFile(archive) as output:
        if output.testzip() is not None:raise ValueError('Archive checksum failed')
        for name,digest in version['files'].items():
            if hashlib.sha256(output.read(package.name+'/'+name)).hexdigest()!=digest:
                raise ValueError('Archive source hash mismatch')
        if any(not include(Path(n).relative_to(package.name)) for n in output.namelist()):
            raise ValueError('Excluded private runtime in ZIP')
    summary={'package':package.name,'zip':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
             'bytes':archive.stat().st_size,'files':len(version['files']),
             'research_papers_included':False,'credentials_included':False,'workbench_state_included':False,
             'sample_result':'synthetic Coding example only; local ZIP, never GitHub'}
    (evidence/'distribution.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
