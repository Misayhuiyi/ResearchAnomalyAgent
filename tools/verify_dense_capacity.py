"""Bounded dense-numeric upper-bound run in an isolated child process."""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'verification' / '2026-10-11-current'


def worker():
    sys.path.insert(0, str(ROOT / 'mvp-demo'))
    import app

    uploads = []
    for file_index in range(20):
        data = bytearray(b'a,b,c,d,e\n')
        row = 0
        while len(data) < 5 * 1024 * 1024 - 60:
            seed = file_index * 100000 + row
            data.extend(f'{seed % 999983},{(seed*7) % 999979},{(seed*11) % 999961},{(seed*13) % 999953},{(seed*17) % 999931}\n'.encode())
            row += 1
        uploads.append((f'dense-{file_index:02d}.csv', bytes(data)))
    with tempfile.TemporaryDirectory(prefix='paper-dense-') as directory:
        started = time.monotonic()
        result = app.scan_files(uploads, runtime_dir=Path(directory))
        print(json.dumps({'files': len(uploads), 'bytes': sum(len(b) for _, b in uploads),
                          'numeric_cells': result['summary']['numeric_cells'],
                          'scan_status': result['scan_status'],
                          'materials_read': sum(m['status'] == 'read' for m in result['materials']),
                          'scan_seconds': round(time.monotonic()-started, 3)}), flush=True)


def main():
    import psutil

    executable = Path(os.environ['PAPER_AUDIT_TEST_PYTHON']).resolve()
    started = time.monotonic()
    peak = 0
    stopped = None
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        child = subprocess.Popen([str(executable), '-X', 'utf8', str(Path(__file__).resolve()), 'worker'],
                                 cwd=ROOT, stdout=stdout, stderr=stderr)
        while child.poll() is None:
            try:
                parent = psutil.Process(child.pid)
                processes = [parent, *parent.children(recursive=True)]
                memory = sum(p.memory_info().rss for p in processes if p.is_running())
                peak = max(peak, memory)
                if memory > 2 * 1024**3 or time.monotonic()-started > 300:
                    stopped = 'memory' if memory > 2 * 1024**3 else 'timeout'
                    for process in reversed(processes):
                        try: process.kill()
                        except psutil.NoSuchProcess: pass
                    break
            except psutil.NoSuchProcess:
                pass
            time.sleep(.2)
        child.wait(timeout=15)
        stdout.seek(0)
        stderr.seek(0)
        raw = stdout.read(16384).decode('utf-8', 'replace')
        error = stderr.read(16384).decode('utf-8', 'replace')
    try:
        result = json.loads(raw) if child.returncode == 0 else None
    except ValueError:
        result = None
    passed = bool(result and result['files'] == 20 and result['materials_read'] == 20
                  and result['scan_status'] == 'complete')
    record = {'at': datetime.now(timezone.utc).isoformat(),
              'scenario': '20 CSV files near 100 MiB total; five numeric columns, unique deterministic rows',
              'exit_code': child.returncode, 'stopped': stopped,
              'wall_seconds': round(time.monotonic()-started, 3),
              'aggregate_rss_peak_bytes': peak, 'result': result,
              'error_type': 'child_error' if error else None, 'passed': passed,
              'limits': {'seconds':300,'aggregate_rss_bytes':2*1024**3}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'dense-capacity.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    worker() if sys.argv[1:] == ['worker'] else main()
