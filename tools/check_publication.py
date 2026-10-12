"""Inspect the exact Git index and history without ever printing credential values."""
import io
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'mvp-demo'))


def git(*args):
    return subprocess.run(['git',*args],cwd=ROOT,check=True,capture_output=True).stdout


def main(working_tree=False):
    try:
        from model_gateway import load_config
        secret=load_config()['secret'].encode('utf-8')
    except ValueError:
        secret=None
    names=git('ls-files','-z',*(['--cached','--others','--exclude-standard'] if working_tree else [])).decode('utf-8').split('\0')
    failures=[];count=0
    banned={'.venv','__pycache__','runtime','delivery','archive','verification','node_modules','test-corpus','test-results'}
    pattern=re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}|BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY')
    for name in filter(None,names):
        path=Path(name)
        env_file=path.name.lower().startswith('.env') and path.name.lower() not in {'.env.example','.env.sample','.env.template'}
        if any(part.lower() in banned for part in path.parts[:-1]) or env_file or path.suffix.lower() in {'.pyc','.sqlite3'}:
            failures.append({'path':name,'reason':'forbidden runtime or credential file'});continue
        blob=(ROOT/name).read_bytes() if working_tree else git('show',':'+name)
        count+=1
        payload=blob
        if path.suffix=='.docx':
            with ZipFile(io.BytesIO(blob)) as z:
                payload=b'\n'.join(z.read(member) for member in z.namelist() if member.endswith('.xml'))
        if (secret and secret in payload) or pattern.search(payload):
            failures.append({'path':name,'reason':'credential pattern; value suppressed'})
    history=git('log','--all','-p','--format=','--no-ext-diff')
    history_secret=bool(secret and secret in history)
    history_pattern=bool(pattern.search(history))
    if history_secret:failures.append({'path':'Git history','reason':'configured credential found; value suppressed'})
    elif history_pattern:failures.append({'path':'Git history','reason':'credential pattern found; value suppressed'})
    git('diff','--cached','--check')
    if working_tree:git('diff','--check')
    report={'indexed_files_checked':count,'actual_key_check_available':secret is not None,
            'history_contains_configured_key':history_secret,
            'history_contains_credential_pattern':history_pattern,
            'history_scope':'text patches; selected files also check DOCX XML',
            'working_tree_including_untracked':working_tree,'failures':failures}
    print(json.dumps(report,ensure_ascii=False))
    return 1 if failures else 0


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--working-tree',action='store_true');args=parser.parse_args()
    sys.exit(main(args.working_tree))
