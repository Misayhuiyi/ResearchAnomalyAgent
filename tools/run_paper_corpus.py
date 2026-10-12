"""Re-run the full FREE browser suite in a fresh folder; never pays for AI.

Usage: python tools/run_paper_corpus.py --node <node.exe> [--node-modules <dir>]
Requires playwright with installed Chromium and the product requirements.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description='重新运行公开论文测试集；不会调用付费模型')
    parser.add_argument('--node',default='node');parser.add_argument('--node-modules',default='')
    parser.add_argument('--port',type=int,default=8897);args=parser.parse_args()
    if not (ROOT/'test-corpus/manifest.json').exists():raise SystemExit('先运行 python tools/prepare_paper_corpus.py')
    if not 1024<=args.port<=65535:raise SystemExit('Invalid local port')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',args.port))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    out=ROOT/'test-results'/('rerun-'+stamp);out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env.update(PAPER_AUDIT_RUNTIME_DIR=str(out/'runtime'),PYTHONIOENCODING='utf-8',
                                     PAPER_CORPUS_RESULTS=str(out),DEMO_URL=f'http://127.0.0.1:{args.port}/')
    if args.node_modules:env['NODE_PATH']=str(Path(args.node_modules).resolve())
    commands=[]
    def run(command):
        started=time.monotonic()
        with (out/'execution.log').open('a',encoding='utf-8') as log:
            proc=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        commands.append({'command':command,'cwd':str(ROOT),'exit_code':proc.returncode,'seconds':round(time.monotonic()-started,3)})
        (out/'commands.json').write_text(json.dumps(commands,ensure_ascii=False,indent=2),encoding='utf-8')
        return proc.returncode
    with (out/'server.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,'-u','mvp-demo/app.py','--port',str(args.port)],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            ready=False
            for _ in range(40):
                if server.poll() is not None:break
                try:
                    with urllib.request.urlopen(env['DEMO_URL']+'api/health',timeout=2) as response:
                        if json.load(response)['ok']:ready=True;break
                except (OSError,ValueError):time.sleep(.5)
            if not ready:raise RuntimeError('服务未就绪，请检查 server.log')
            browser=run([args.node,'tools/verify_paper_corpus.cjs'])
            evidence=run([sys.executable,'tools/check_corpus_evidence.py',str(out)])
            print('测试记录保留在：'+str(out));return max(browser,evidence)
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':raise SystemExit(main())
