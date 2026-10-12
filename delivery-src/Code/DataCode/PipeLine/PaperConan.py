"""Single application's caller; no workflow branching or downstream reads."""
from pathlib import Path
import json
import app
from delivery_support import validate_inputs


def scan_materials(stage: Path, output: Path):
    uploads,profile,checks,note=validate_inputs(stage)
    result=app.scan_files(uploads,profile,runtime_dir=output,extra_checks=checks)
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
