"""Explicit browser-test fixture, never a product startup or network bypass."""
import os
import json
import time
from functools import partial
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
service_root=ROOT/'mvp-demo'
if os.environ.get('PAPER_AUDIT_DELIVERY'):
    package=Path(os.environ['PAPER_AUDIT_DELIVERY']).resolve()
    if package.parent!=ROOT/'delivery' or not package.name.startswith('PaperAudit-'):
        raise SystemExit('Select a local candidate under delivery.')
    service_root=package/'PaperAudit_Coding'/'Code'/'DataCode'
sys.path.insert(0, str(service_root))
import app
import public_materials
import agent_service
from budget_store import MODEL, VERSION
from model_gateway import ENDPOINT
from public_fetch import FetchResult, MaterialError


def fixture_fetch(url):
    if url == "https://fixtures.example/paper":
        return FetchResult(url, b'''<meta name="citation_title" content="Fixture paper &lt;script&gt;">
            <a href="/public-data.csv">Source data</a><a href="/needs-login.pdf">PDF</a>''', {"content-type": "text/html"})
    if url == "https://fixtures.example/public-data.csv":
        return FetchResult(url, (ROOT / "mvp-demo/samples/fixed_shift_demo.csv").read_bytes(), {"content-type": "text/csv"})
    if url == "https://fixtures.example/needs-login.pdf":
        return FetchResult(url, b"<html>Sign in</html>", {"content-type": "text/html"})
    raise MaterialError("测试站点未提供此材料。")


def fixture_config():
    return {'endpoint':ENDPOINT,'secret':'TEST-FIXTURE-NOT-A-KEY','valid_until':time.time()+300,
            'price':{'model':MODEL,'version':VERSION,'currency':'CNY','unit':'per_million_tokens',
                     'input':'2','output':'3','reference':'SYNTHETIC BROWSER TEST ONLY'}}


def fixture_model(secret, payload):
    request=json.loads(payload);data=json.loads(request['messages'][1]['content'])
    sid,source=next(iter(data['sources'].items()))
    suggestions=[{'finding_id':data['findings'][0]['id'],'reason':'needs_context',
                  'citations':[{'source_id':sid,'quote':source['text']}]}] if data['findings'] else []
    return {'model':MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'suggestions':suggestions,'tool_requests':[]})}}],
            'usage':{'prompt_tokens':100,'completion_tokens':100}}


class FixtureHandler(app.DemoHandler):
    def do_GET(self):
        if self.path == "/__fixture__":
            if self._local_request():
                self._json(200, {"fixture": True, "network": "substituted", "engine": "real"})
            return
        super().do_GET()


if __name__ == "__main__":
    if not os.environ.get("PAPER_AUDIT_RUNTIME_DIR"):
        raise SystemExit("Test fixture requires a disposable PAPER_AUDIT_RUNTIME_DIR.")
    server = app.ThreadingHTTPServer(("127.0.0.1", 8877), FixtureHandler)
    app.restore_scan_jobs()
    print("TEST FIXTURE ONLY: http://127.0.0.1:8877; external pages substituted, scan engine real", flush=True)
    try:
        with patch.object(public_materials, "fetch_public", side_effect=fixture_fetch), patch.object(
                agent_service,'AgentService',partial(agent_service.AgentService,config_loader=fixture_config,transport=fixture_model)):
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
