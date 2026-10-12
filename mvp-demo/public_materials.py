"""DOI/landing-page discovery and explicit, source-preserving material imports."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urljoin, urlsplit

from platform_ports import Actor, MaterialStorePort
from public_fetch import FetchResult, MaterialError, fetch_public, public_url


EXTENSIONS = {".pdf", ".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".xlsb", ".docx"}
MIME_EXTENSIONS = {"application/pdf": ".pdf", "text/csv": ".csv", "text/tab-separated-values": ".tsv",
                   "application/vnd.ms-excel": ".xls",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}


def normalize_reference(value: str) -> str:
    if not isinstance(value, str):
        raise MaterialError("请输入 DOI 或论文链接。")
    value = value.strip()
    doi = re.sub(r"(?i)^doi:\s*", "", value)
    if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return "https://doi.org/" + quote(doi, safe="/().-_;:")
    return public_url(value)


def is_html(result: FetchResult) -> bool:
    prefix = result.content[:1024].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    return "html" in result.headers.get("content-type", "").lower() or bool(re.search(br"<(?:!doctype\s+html|html|head|body)\b", prefix))


def filename_for(result: FetchResult) -> str:
    message = Message()
    message["Content-Disposition"] = result.headers.get("content-disposition", "")
    name = message.get_filename() or unquote(PurePosixPath(urlsplit(result.url).path).name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "论文材料").strip(". ")[:150]
    extension = PurePosixPath(name).suffix.lower()
    mime = result.headers.get("content-type", "").split(";", 1)[0].lower().strip()
    if extension not in EXTENSIONS:
        extension = ".pdf" if result.content.startswith(b"%PDF-") else MIME_EXTENSIONS.get(mime)
        if not extension:
            raise MaterialError("该链接未返回支持的表格、PDF 或 Word 文件，请直接上传。")
        name = (name or "论文材料") + extension
    if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", PurePosixPath(name).stem):
        name = "材料_" + name
    return name


class LandingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.title, self.citation_title, self.doi, self.in_title = "", "", "", False
        self.anchor = None
        self.anchor_text = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            content = values.get("content") or ""
            if name == "citation_pdf_url" and len(self.links) < 1000:
                self.links.append((content, "论文全文"))
            elif name == "citation_title":
                self.citation_title = content[:500]
            elif name == "citation_doi":
                self.doi = content[:300]
        elif tag == "title":
            self.in_title = True
        elif tag == "a":
            self.anchor, self.anchor_text = values.get("href"), ""

    def handle_data(self, data):
        if self.in_title and len(self.title) < 500:
            self.title += data[:500 - len(self.title)]
        if self.anchor and len(self.anchor_text) < 200:
            self.anchor_text += data[:200 - len(self.anchor_text)]

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.anchor:
            if len(self.links) < 1000:
                self.links.append((self.anchor, self.anchor_text.strip()))
            self.anchor = None


def discover(reference: str) -> dict:
    requested = normalize_reference(reference)
    result = fetch_public(requested)
    if not is_html(result):
        return {"title": filename_for(result), "source_url": result.url, "doi": "", "candidates": [
            {"url": result.url, "label": filename_for(result)}], "message": "请核对材料后加入本次筛查。"}
    parser = LandingParser()
    parser.feed(result.content.decode("utf-8", errors="replace"))
    candidates, seen = [], set()
    for link, label in parser.links:
        try:
            target = public_url(urljoin(result.url, link))
        except MaterialError:
            continue
        if target in seen:
            continue
        ext = PurePosixPath(unquote(urlsplit(target).path)).suffix.lower()
        if ext not in EXTENSIONS and not re.search(r"(?i)(论文全文|supplement|supporting|附[件表]|补充|\bpdf\b|\bcsv\b|\bxlsx\b)", label):
            continue
        seen.add(target)
        candidates.append({"url": target, "label": label[:160] or unquote(PurePosixPath(urlsplit(target).path).name)[:160]})
        if len(candidates) >= 20:
            break
    return {"title": parser.citation_title.strip() or parser.title.strip() or "公开材料", "doi": parser.doi, "source_url": result.url,
            "candidates": candidates,
            "message": "仅列出当前页面发现的下载链接，不代表已获取全部材料。" if candidates else
                       "当前页面未找到可直接获取的材料。可在原网站下载后上传。"}


def import_material(url: str, store: MaterialStorePort, actor: Actor) -> dict:
    requested = public_url(url)
    result = fetch_public(requested)
    if is_html(result):
        raise MaterialError("该链接返回网页而非文件，请在原网站下载材料后上传。")
    if not result.content:
        raise MaterialError("网站返回的文件为空，请直接上传。")
    filename = filename_for(result)
    extension = PurePosixPath(filename).suffix.lower()
    if extension == ".pdf" and b"%PDF-" not in result.content[:1024]:
        raise MaterialError("网站未返回有效的 PDF 文件，请直接上传材料。")
    if extension in {".xlsx", ".xlsm", ".xlsb", ".docx"} and not result.content.startswith(b"PK\x03\x04"):
        raise MaterialError("网站未返回有效的表格或 Word 文件，请直接上传材料。")
    if extension in {".csv", ".tsv"} and (b"\x00" in result.content[:8192] or result.content.lstrip().startswith(b"<")):
        raise MaterialError("网站未返回有效的文本表格，请直接上传材料。")
    metadata = store.save(actor, filename, result.content, {
        "kind": "public_download", "requested_url": requested, "source_url": result.url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    })
    return {key: value for key, value in metadata.items() if key != "owner"}
