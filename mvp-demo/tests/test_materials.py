"""Public acquisition contracts. Network substitutes are explicit; engine test is real."""
import base64
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app
import public_fetch as net
import public_materials as materials
from platform_ports import Actor, LOCAL_ACTOR, LocalMaterialStore


CSV = b"group,value\nA,1.2\nB,2.4\n"


class Response:
    def __init__(self, body=b"", status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}
    def getheaders(self):
        return list(self.headers.items())
    def read1(self, count):
        return self.body.read(count)


class PublicFetchTests(unittest.TestCase):
    def test_url_rejects_private_credentials_ports_and_schemes(self):
        for url in ["file:///c:/secret", "ftp://example.org/data", "http://127.0.0.1/", "http://[::1]/",
                    "http://10.0.0.1/", "http://169.254.169.254/", "http://localhost/", "https://user:pass@example.org/",
                    "https://example.org:8443/", "https://example.org/\r\nx", "http://[fe80::1%25eth0]/"]:
            with self.subTest(url=url), self.assertRaises(net.MaterialError):
                net.public_url(url)

    def test_doi_and_url_normalization(self):
        self.assertEqual("https://doi.org/10.1234/example", materials.normalize_reference("doi: 10.1234/example"))
        self.assertEqual("https://example.org/a%20b.pdf", materials.normalize_reference("https://example.org/a%20b.pdf#page=2"))

    def test_dns_rejects_nonpublic_or_mixed_answers(self):
        for ips in [["127.0.0.1"], ["8.8.8.8", "10.0.0.1"], ["0.0.0.0"], ["224.0.0.1"]]:
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]
            with patch.object(socket, "getaddrinfo", return_value=records), self.assertRaises(net.MaterialError):
                net.resolve_public("example.org", 443, 2)

    def test_connection_pins_checked_ip_but_keeps_tls_hostname(self):
        sock = MagicMock()
        context = MagicMock()
        with patch.object(socket, "create_connection", return_value=sock) as connect, patch.object(net.ssl, "create_default_context", return_value=context):
            connection = net.PinnedConnection("example.org", "8.8.8.8", 443, 3, True)
            connection.connect()
            connect.assert_called_once_with(("8.8.8.8", 443), 3)
            context.wrap_socket.assert_called_once_with(sock, server_hostname="example.org")

    def test_redirect_revalidates_target_and_never_calls_private_ip(self):
        connection = MagicMock()
        connection.getresponse.return_value = Response(status=302, headers={"Location": "http://127.0.0.1/secret"})
        with patch.object(net, "resolve_public", return_value="8.8.8.8"), patch.object(net, "PinnedConnection", return_value=connection) as factory:
            with self.assertRaises(net.MaterialError):
                net.fetch_public("https://example.org/paper")
            self.assertEqual(1, factory.call_count)
            connection.close.assert_called()

    def test_fetch_size_status_and_compression_boundaries(self):
        for response in [Response(b"12345"), Response(b"123", headers={"Content-Length": "10"}),
                         Response(b"12", headers={"Content-Length": "3"}),
                         Response(status=403), Response(headers={"Content-Encoding": "gzip"})]:
            connection = MagicMock()
            connection.getresponse.return_value = response
            with patch.object(net, "resolve_public", return_value="8.8.8.8"), patch.object(net, "PinnedConnection", return_value=connection):
                with self.assertRaises(net.MaterialError):
                    net.fetch_public("https://example.org/a.csv", max_bytes=4)

    def test_fetch_reads_exact_limit_and_does_not_forward_secrets(self):
        connection = MagicMock()
        connection.getresponse.return_value = Response(b"1234")
        with patch.object(net, "resolve_public", return_value="8.8.8.8"), patch.object(net, "PinnedConnection", return_value=connection):
            result = net.fetch_public("https://example.org/a.csv", max_bytes=4)
            self.assertEqual(b"1234", result.content)
            headers = connection.request.call_args.kwargs["headers"]
            self.assertNotIn("Authorization", headers)
            self.assertNotIn("Cookie", headers)
            self.assertEqual("identity", headers["Accept-Encoding"])

    def test_deadline_and_redirect_loop_stop(self):
        with self.assertRaises(net.MaterialError):
            net.fetch_public("https://example.org/a", timeout=0)
        connection = MagicMock()
        connection.getresponse.return_value = Response(status=302, headers={"Location": "/a"})
        with patch.object(net, "resolve_public", return_value="8.8.8.8"), patch.object(net, "PinnedConnection", return_value=connection):
            with self.assertRaises(net.MaterialError):
                net.fetch_public("https://example.org/a")


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LocalMaterialStore(Path(self.temp.name) / "materials")

    def import_csv(self):
        fetched = net.FetchResult("https://example.org/values.csv", CSV, {"content-type": "text/csv"})
        with patch.object(materials, "fetch_public", return_value=fetched):
            return materials.import_material("https://example.org/download", self.store, LOCAL_ACTOR)

    def test_landing_discovery_metadata_dedupe_relative_and_unsafe_links(self):
        body = b'''<meta name="citation_title" content="Example paper"><meta name="citation_doi" content="10.1234/example">
        <meta name="citation_pdf_url" content="/paper.pdf"><a href="/paper.pdf">PDF</a>
        <a href="/data.csv">Source data</a><a href="http://127.0.0.1/a.csv">Private</a>
        <a href="javascript:alert(1)">PDF</a><a href="/login">Sign in</a>'''
        with patch.object(materials, "fetch_public", return_value=net.FetchResult("https://example.org/paper", body, {"content-type": "text/html"})):
            result = materials.discover("10.1234/example")
        self.assertEqual("Example paper", result["title"])
        self.assertEqual(["https://example.org/paper.pdf", "https://example.org/data.csv"], [item["url"] for item in result["candidates"]])
        self.assertIn("不代表", result["message"])

    def test_no_downloads_and_html_instead_of_file_are_not_success(self):
        response = net.FetchResult("https://example.org/a.pdf", b"<html>Login</html>", {"content-type": "application/pdf"})
        with patch.object(materials, "fetch_public", return_value=response):
            self.assertEqual([], materials.discover(response.url)["candidates"])
            with self.assertRaisesRegex(net.MaterialError, "网页"):
                materials.import_material(response.url, self.store, LOCAL_ACTOR)

    def test_filename_is_safe_and_mime_handles_extensionless_pdf(self):
        result = net.FetchResult("https://example.org/download", b"%PDF-1.7", {"content-disposition": 'attachment; filename="../../CON.pdf"'})
        name = materials.filename_for(result)
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        app.validate_upload(name, result.content, "review")
        self.assertTrue(materials.filename_for(net.FetchResult(result.url, result.content, {})).endswith(".pdf"))

    def test_disguised_download_types_are_rejected(self):
        for name, content in [("a.pdf", b"not a pdf"), ("a.xlsx", b"sign in"), ("a.csv", b"<script>login()</script>")]:
            response = net.FetchResult("https://example.org/" + name, content, {})
            with patch.object(materials, "fetch_public", return_value=response), self.assertRaises(net.MaterialError):
                materials.import_material(response.url, self.store, LOCAL_ACTOR)

    def test_snapshot_survives_new_store_and_repeat_import_is_idempotent(self):
        first, second = self.import_csv(), self.import_csv()
        self.assertEqual(first["source_id"], second["source_id"])
        self.assertNotIn("owner", first)
        metadata, content = LocalMaterialStore(self.store.root).load(LOCAL_ACTOR, first["source_id"])
        self.assertEqual(CSV, content)
        self.assertEqual("https://example.org/values.csv", metadata["provenance"]["source_url"])
        self.assertTrue(metadata["provenance"]["retrieved_at"])

    def test_ownership_invalid_id_and_tamper_rejected(self):
        item = self.import_csv()
        for actor, key in [(Actor("other", "single-user"), item["source_id"]), (LOCAL_ACTOR, "../secret")]:
            with self.assertRaises(net.MaterialError):
                self.store.load(actor, key)
        (self.store.root / item["source_id"] / "content").write_bytes(b"x" * len(CSV))
        with self.assertRaisesRegex(net.MaterialError, "发生变化"):
            self.store.load(LOCAL_ACTOR, item["source_id"])

    def test_staging_quota_includes_partial_import(self):
        folder = self.store.root / ("a" * 32)
        folder.mkdir(parents=True)
        (folder / "content").write_bytes(CSV)
        self.store.max_items = 1
        with self.assertRaisesRegex(net.MaterialError, "较多"):
            self.import_csv()

    def test_submission_combines_upload_and_snapshot_and_rejects_spoofing(self):
        item = self.import_csv()
        with patch.object(app, "material_store", return_value=self.store):
            uploads, profile, sources = app.decode_submission({"files": [{"source_id": item["source_id"]},
                {"filename": "extra.csv", "content_base64": base64.b64encode(CSV).decode(), "source_url": "fake"}]})
            self.assertEqual(["values.csv", "extra.csv"], [name for name, _ in uploads])
            self.assertEqual(1, len(sources))
            with self.assertRaises(app.DemoError):
                app.decode_submission({"files": [{"source_id": item["source_id"], "content_base64": "fake"}]})
            with self.assertRaisesRegex(app.DemoError, "重名"):
                app.decode_submission({"files": [{"source_id": item["source_id"]}] * 2})

    def test_real_scan_persists_original_source_and_report(self):
        sample = (ROOT / "samples" / "fixed_shift_demo.csv").read_bytes()
        fetched = net.FetchResult("https://example.org/original.csv", sample, {"content-type": "text/csv"})
        with patch.object(materials, "fetch_public", return_value=fetched):
            item = materials.import_material(fetched.url, self.store, LOCAL_ACTOR)
        with patch.object(app, "material_store", return_value=self.store):
            uploads, profile, sources = app.decode_submission({"files": [{"source_id": item["source_id"]}]})
        runtime = Path(self.temp.name) / "scans"
        result = app.scan_files(uploads, profile, runtime_dir=runtime, material_sources=sources)
        saved = json.loads((runtime / result["scan_id"] / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(item["sha256"], saved["material_sources"][0]["sha256"])
        self.assertIn(fetched.url, (runtime / result["scan_id"] / "report.html").read_text(encoding="utf-8"))
        self.assertTrue(result["findings"])


class LocalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DemoHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        self.addCleanup(connection.close)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, response.read()

    def test_wrong_host_or_cross_origin_is_rejected(self):
        self.assertEqual(403, self.request("/", headers={"Host": "evil.example"})[0])
        self.assertEqual(403, self.request("/api/materials/discover", "POST", "{}", {"Origin": "https://evil.example", "Content-Type": "application/json"})[0])

    def test_import_requires_explicit_paper_confirmation(self):
        with patch.object(materials, "import_material") as importer:
            status, _ = self.request("/api/materials/import", "POST", '{"url":"https://example.org/a.csv"}', {"Content-Type": "application/json"})
        self.assertEqual(400, status)
        importer.assert_not_called()

    def test_discovery_api_and_new_script_are_served(self):
        with patch.object(materials, "discover", return_value={"candidates": []}):
            status, content = self.request("/api/materials/discover", "POST", '{"reference":"10.1234/example"}', {"Content-Type": "application/json"})
        self.assertEqual(200, status)
        self.assertTrue(json.loads(content)["ok"])
        self.assertEqual(200, self.request("/public-materials.js")[0])

    def test_cloud_mode_fails_closed_and_lan_binding_is_disabled(self):
        with patch.dict(os.environ, {"PAPER_AUDIT_PLATFORM_MODE": "baiyin"}), self.assertRaises(app.DemoError):
            app.run_server()
        with patch.dict(os.environ, {"PAPER_AUDIT_PLATFORM_MODE": "local"}), self.assertRaises(app.DemoError):
            app.run_server("0.0.0.0")


if __name__ == "__main__":
    unittest.main()
