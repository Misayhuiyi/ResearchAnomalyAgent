"""Administrator setup: hidden input, free model discovery, current-user encryption.

No inference, paper upload, fee authorization, or automatic retry is performed.
"""
import getpass
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mvp-demo'))
from local_credentials import protect_secret
from model_gateway import ENDPOINT, load_config


def main():
    if os.name != 'nt' or not os.environ.get('LOCALAPPDATA') or not sys.stdin.isatty():
        raise ValueError('请在 Windows 本机交互终端运行；不接受命令行或管道传入密钥。')
    destination = Path(os.environ['LOCALAPPDATA']) / 'PaperAudit' / 'DeepSeek'
    path = destination / 'model.json'
    if path.exists():
        if input('替换本机模型配置？输入 REPLACE 确认：') != 'REPLACE':
            raise ValueError('未替换已有配置。')
    key = getpass.getpass('DeepSeek API key (hidden): ')
    protected = protect_secret(key)
    connection = http.client.HTTPSConnection('api.deepseek.com', timeout=20, context=ssl.create_default_context())
    try:
        connection.request('GET', '/models', headers={'Authorization': 'Bearer ' + key})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('模型查询未通过，HTTP ' + str(response.status) + '；未保存配置。')
        raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError('模型列表超出范围；未保存配置。')
        models = json.loads(raw).get('data', [])
        if not any(m.get('id') == 'deepseek-flash' and m.get('name') == 'DeepSeek-V4.1-Flash' for m in models):
            raise ValueError('接口未确认指定模型及版本；未保存配置。')
    finally:
        connection.close()
        key = None
    # Date-pinned admin price review: no automatic prolongation of stale rates.
    # Official peak, cache-miss USD rates checked 2026-10-11. Recheck before extending.
    valid_until = 1794355200  # 2026-11-11 00:00:00 UTC
    if not time.time() < valid_until <= time.time() + 31 * 86400:
        raise ValueError('内置价格核验期已过或当前时间不符，请管理员重新核验价格及有效期。')
    config = {'endpoint': ENDPOINT, 'verified_model_name': 'DeepSeek-V4.1-Flash',
              'valid_until': valid_until, 'protected_secret': protected,
              'price': {'model': 'deepseek-flash', 'version': 'DeepSeek V4.1 Flash',
                        'currency': 'USD', 'unit': 'per_million_tokens', 'input': '0.30', 'output': '1.20',
                        'reference': 'https://api-docs.deepseek.com/quick_start/pricing/ ; 2026-10-11 peak/cache-miss upper bound, not provider invoice'}}
    # Only this user and SYSTEM can read the folder; no credentials in arguments.
    permission_script = '''$ErrorActionPreference='Stop'
$dir=Join-Path $env:LOCALAPPDATA 'PaperAudit\\DeepSeek'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
foreach($id in @($sid,([System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')))) {
 $acl.AddAccessRule([System.Security.AccessControl.FileSystemAccessRule]::new($id,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
}
[System.IO.Directory]::SetAccessControl($dir,$acl)
'''
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', permission_script],
                   check=True, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    staging = destination / 'model.pending'
    staging.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    load_config({'PAPER_AUDIT_MODEL_CONFIG': str(staging)})
    staging.replace(path)
    print('Configured DeepSeek-V4.1-Flash (deepseek-flash); encrypted for current Windows user.')
    print('Model discovery: HTTP 200. Paid inference calls: 0. Paper uploads: 0.')
    print('Config:', path)


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('配置未完成，请检查网络、目录权限和本机环境。密钥未输出。', file=sys.stderr)
        sys.exit(1)
