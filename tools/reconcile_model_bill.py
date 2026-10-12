"""Offline administrator command; reads an explicit receipt outside user uploads.

Stop the application before running. It never calls the model or changes research
results. Filesystem access to the private runtime is the local administrator gate.
"""
import hashlib
import json
import os
import sys
from pathlib import Path
module_root=Path(__file__).resolve().parent
if not (module_root/'budget_store.py').is_file():module_root=module_root.parent/'mvp-demo'
sys.path.insert(0,str(module_root))
from budget_store import BudgetStore
from platform_ports import Actor
from runtime_guard import RuntimeLease


def main():
    if os.environ.get('PAPER_AUDIT_OPERATOR_CONFIRM') != 'reconcile-provider-bill':
        raise SystemExit('仅管理员在停止应用后明确确认对账，不向普通用户开放。')
    root=Path(os.environ['PAPER_AUDIT_RUNTIME_DIR']).resolve(strict=True)
    request_path=Path(os.environ['PAPER_AUDIT_RECONCILIATION_FILE']).resolve(strict=True)
    request=json.loads(request_path.read_text(encoding='utf-8-sig'))
    if request.get('confirmed') is not True: raise ValueError('须人工确认服务方账单。')
    receipt=Path(request['receipt_path']).resolve(strict=True)
    if receipt.is_relative_to(root) or receipt.stat().st_size > 5*1024*1024:
        raise ValueError('账单须保存在运行材料目录以外，且不超过 5 MB。')
    receipt_hash=hashlib.sha256(receipt.read_bytes()).hexdigest()
    if receipt_hash != request['receipt_sha256']: raise ValueError('账单内容已变化。')
    actor=Actor(request['tenant'],request['owner'])
    with RuntimeLease(root):
        result=BudgetStore(root).reconcile(actor,request['budget_id'],request['call_key'],
              request['actual_micros'],request['currency'],receipt_hash,request['reviewer'],request['provider_reference'])
    print(json.dumps({'reconciled':True,'actual_micros':result['actual_micros'],
                      'model_result_recovered':False,'automatic_retry':False},ensure_ascii=False))


if __name__=='__main__': main()
