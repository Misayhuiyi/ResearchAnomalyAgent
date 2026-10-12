"""Real public paper regression. No model call and no fabricated misconduct label."""
import csv
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mvp-demo'))
import app

OUT = ROOT / 'docs/verification/2026-09-30-real-paper'
MATERIALS = OUT / 'materials'
EXPECTED = {
    'Gorman2014.pdf': 'cc2e8e08db55a110d5e849db35f7665e9c18c0c06cd7fce49dd3007846f3820f',
    'penguins_raw.csv': '144f623143c9360fd77322a4f86acb06dc198814dbd2669724c63e6457b907bd',
}


def main():
    started = time.monotonic()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    run = OUT / 'runs' / stamp
    run.mkdir(parents=True, exist_ok=False)
    uploads = [(name, (MATERIALS / name).read_bytes()) for name in EXPECTED]
    for name, data in uploads:
        assert hashlib.sha256(data).hexdigest() == EXPECTED[name], 'Public snapshot changed'
    rows = list(csv.DictReader((MATERIALS / 'penguins_raw.csv').open(encoding='utf-8')))
    counts = Counter(r['Species'].split()[0] for r in rows)
    assert len(rows) == 344 and counts == {'Adelie': 152, 'Chinstrap': 68, 'Gentoo': 124}
    result = app.scan_files(uploads, runtime_dir=run)
    findings = result['findings']
    # Exact raw cell verification independent of the engine's rounded values.
    mismatches = []
    checked = 0
    missing_evidence = []
    for finding in findings:
        if finding.get('file') != 'penguins_raw.csv':
            continue
        if finding['kind']=='identical_after_rounding' and len(finding['evidence']['focus_cells']) != finding['n']:
            missing_evidence.append({'finding': finding['id'], 'expected': finding['n'],
                                     'shown': len(finding['evidence']['focus_cells'])})
        for cell in finding.get('evidence', {}).get('focus_cells', []):
            try:
                expected = float(rows[int(cell['row_idx'])-2][cell['column']])
                checked += 1
                if expected != float(cell['original']):
                    mismatches.append(cell)
            except (KeyError, ValueError, IndexError, TypeError):
                mismatches.append(cell)
    record = {'at': datetime.now(timezone.utc).isoformat(), 'paper_doi': '10.1371/journal.pone.0090081',
              'hashes': EXPECTED, 'scan_id': result['scan_id'], 'run_dir': str(run),
              'duration_seconds': round(time.monotonic()-started, 3),
              'sample_count': len(rows), 'species_counts': dict(counts),
              'materials': result['materials'], 'scan_status': result['scan_status'],
              'summary': result['summary'], 'kinds': dict(Counter(f['kind'] for f in findings)),
              'focus_cells_checked': checked, 'source_mismatches': mismatches,
              'missing_evidence': missing_evidence,
              'model_calls': 0, 'human_acceptance': 'pending',
              'quality_boundary': 'One public paper; source/count verification, not misconduct truth or independent final UAT.'}
    (run / 'verification.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))
    assert not mismatches, 'Evidence differs from original CSV'
    assert not missing_evidence, 'Known real sample has incomplete source evidence'
    assert next(m for m in result['materials'] if m['filename']=='penguins_raw.csv')['status']=='read'


if __name__ == '__main__':
    main()
