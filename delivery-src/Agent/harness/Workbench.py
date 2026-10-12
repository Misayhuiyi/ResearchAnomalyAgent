"""No-argument local workbench launcher; state never writes into Code."""
import os
import sys
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[2]
CODING=PACKAGE/'PaperAudit_Coding'
sys.dont_write_bytecode=True
os.environ.setdefault('PAPER_AUDIT_RUNTIME_DIR',str(PACKAGE/'PaperAudit_Agent'/'Result'/'WorkbenchState'))
sys.path.insert(0,str(CODING/'Code'/'DataCode'))
import app


if __name__=='__main__':
    app.run_server(port=int(os.environ.get('PAPER_AUDIT_PORT','8765')))
