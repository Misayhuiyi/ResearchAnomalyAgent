"""Synthetic upper-upload-boundary experiment, not representative paper quality."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHONUTF8']='1'
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')


def worker():
    sys.path.insert(0,str(ROOT/'mvp-demo'))
    import app
    rng=random.Random(930)
    uploads=[]
    for i in range(20):
        parts=[b'control,measurement,note\n'];remaining=5*1024*1024-len(parts[0])
        while remaining:
            prefix=f'{rng.uniform(10,100):.5f},{rng.uniform(20,200):.5f},'.encode()
            size=min(60000,remaining)
            if remaining-size and remaining-size<100: size=remaining
            if size<len(prefix)+1:raise RuntimeError('Invalid fixture sizing')
            parts.append(prefix+b'x'*(size-len(prefix)-1)+b'\n');remaining-=size
        uploads.append((f'capacity-{i:02d}.csv',b''.join(parts)))
    assert sum(len(data) for _,data in uploads)==100*1024*1024
    with tempfile.TemporaryDirectory(prefix='paper-capacity-') as directory:
        result=app.scan_files(uploads,runtime_dir=Path(directory))
        print(json.dumps({'input_bytes':sum(len(data) for _,data in uploads),'files':len(uploads),
                          'scan_status':result['scan_status'],'materials':result['materials'],
                          'numeric_cells':result['summary']['numeric_cells'],
                          'evidence_limits':result['evidence_limits']}))


def main():
    import psutil
    executable=os.environ['PAPER_AUDIT_TEST_PYTHON']
    os.environ.setdefault('PAPERCONAN_BIN',str(Path(executable).parent/'paperconan.exe'))
    started=time.monotonic();peak=0;stopped=None
    with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
        child=subprocess.Popen([executable,str(Path(__file__).resolve()),'worker'],cwd=ROOT,stdout=stdout,stderr=stderr)
        while child.poll() is None:
            try:
                processes=[psutil.Process(child.pid)]+psutil.Process(child.pid).children(recursive=True)
                memory=sum(p.memory_info().rss for p in processes if p.is_running())
                peak=max(peak,memory)
                if memory>2*1024**3 or time.monotonic()-started>240:
                    stopped='memory' if memory>2*1024**3 else 'timeout'
                    for process in reversed(processes):
                        try:process.kill()
                        except psutil.NoSuchProcess:pass
                    break
            except psutil.NoSuchProcess: pass
            time.sleep(.1)
        child.wait(timeout=15);stdout.seek(0);stderr.seek(0)
        output=stdout.read().decode('utf-8','replace');error=stderr.read().decode('utf-8','replace')
    data=json.loads(output) if child.returncode==0 else None
    passed=child.returncode==0 and data['files']==20 and all(m['status']=='read' for m in data['materials'])
    record={'at':datetime.now(timezone.utc).isoformat(),'data':'synthetic 20 CSV files, each 5 MiB, mostly text notes; seed 930',
            'thresholds_declared':{'wall_seconds':240,'aggregate_rss_bytes':2*1024**3},
            'measured':{'wall_seconds':round(time.monotonic()-started,3),'aggregate_rss_peak_bytes':peak},
            'exit_code':child.returncode,'stopped':stopped,'result':data,'error':error[-5000:],'passed':passed,
            'boundary':'Upload-byte boundary with sparse numeric data, not dense tables, all file formats, concurrency or platform capacity.'}
    out=ROOT/'docs/verification/2026-09-30-current';out.mkdir(parents=True,exist_ok=True)
    (out/'capacity.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__=='__main__':
    worker() if len(sys.argv)>1 and sys.argv[1]=='worker' else main()
