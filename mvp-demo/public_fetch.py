"""Bounded public HTTP reads; never use ambient proxies, credentials or private IPs."""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


class MaterialError(ValueError):
    """A safe, actionable material-acquisition error."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    content: bytes
    headers: dict[str, str]


DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="public-dns")
DNS_SLOTS = threading.BoundedSemaphore(4)
FETCH_SLOTS = threading.BoundedSemaphore(3)
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_HTML_BYTES = 2 * 1024 * 1024


def public_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise MaterialError("请输入有效的公开论文链接。")
    if re.search(r"[\x00-\x20\x7f\\]", value):
        raise MaterialError("链接包含不支持的字符。")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        if parts.scheme.lower() not in {"http", "https"} or not host or parts.username is not None or parts.password is not None:
            raise ValueError
        if port is not None and port != (443 if parts.scheme.lower() == "https" else 80):
            raise ValueError
        if "%" in host or host.lower().rstrip(".") in {"localhost", "metadata.google.internal"}:
            raise ValueError
        encoded_host = host.encode("idna").decode("ascii").lower().rstrip(".")
        try:
            address = ipaddress.ip_address(encoded_host)
        except ValueError:
            address = None
        if address is not None and not allowed_ip(str(address)):
            raise ValueError
        authority = f"[{encoded_host}]" if ":" in encoded_host else encoded_host
        return urlunsplit((parts.scheme.lower(), authority,
                           quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~"),
                           quote(parts.query, safe="%:@!$&'()*+,;=/?-._~"), ""))
    except (ValueError, UnicodeError) as exc:
        raise MaterialError("仅支持不含账号信息的公网 HTTP/HTTPS 链接。") from exc


def allowed_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return address.is_global and not (address.is_multicast or address.is_reserved or address.is_unspecified)


def resolve_public(host: str, port: int, timeout: float) -> str:
    if not DNS_SLOTS.acquire(blocking=False):
        raise MaterialError("正在获取其他材料，请稍后重试。")
    future = DNS_POOL.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    future.add_done_callback(lambda _: DNS_SLOTS.release())
    try:
        records = future.result(timeout=max(0.1, min(timeout, 8)))
    except (FutureTimeout, OSError) as exc:
        raise MaterialError("无法解析论文网站地址，请稍后重试或上传文件。") from exc
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not allowed_ip(address) for address in addresses):
        raise MaterialError("该链接不是可访问的公网材料地址。")
    return addresses[0]


class PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float, tls: bool):
        super().__init__(host, port, timeout=timeout)
        self.target_ip, self.tls = ip, tls

    def connect(self) -> None:
        # Connect to the checked IP, not a second DNS lookup of the host.
        self.sock = socket.create_connection((self.target_ip, self.port), self.timeout)
        if self.tls:
            try:
                self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
            except BaseException:
                self.sock.close()
                raise


def fetch_public(url: str, max_bytes: int = MAX_FILE_BYTES, timeout: float = 40) -> FetchResult:
    if not FETCH_SLOTS.acquire(blocking=False):
        raise MaterialError("正在获取其他材料，请稍后重试。")
    try:
        return _fetch(url, max_bytes, time.monotonic() + timeout)
    finally:
        FETCH_SLOTS.release()


def _fetch(url: str, max_bytes: int, deadline: float) -> FetchResult:
    visited: set[str] = set()
    for _ in range(6):
        url = public_url(url)
        if url in visited:
            raise MaterialError("论文网站重复跳转，请直接上传文件。")
        visited.add(url)
        parts = urlsplit(url)
        port = 443 if parts.scheme == "https" else 80
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MaterialError("获取材料超时，请重试或直接上传。")
        address = resolve_public(parts.hostname, port, remaining)
        connection = PinnedConnection(parts.hostname, address, port,
                                      max(0.1, min(10, deadline - time.monotonic())), parts.scheme == "https")
        try:
            connection.request("GET", urlunsplit(("", "", parts.path, parts.query, "")), headers={
                "User-Agent": "PaperAudit/0.2 (public research material retrieval)",
                "Accept-Encoding": "identity", "Accept": "*/*", "Connection": "close",
            })
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            if response.status in {301, 302, 303, 307, 308}:
                target = headers.get("location")
                if not target:
                    raise MaterialError("论文网站未提供有效的跳转地址。")
                url = urljoin(url, target)
                continue
            if response.status != 200:
                raise MaterialError(f"网站未提供可公开读取的材料（{response.status}），可直接上传文件。")
            if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                raise MaterialError("网站返回了不支持的压缩内容，请直接上传文件。")
            limit = min(max_bytes, MAX_HTML_BYTES) if "html" in headers.get("content-type", "").lower() else max_bytes
            try:
                if int(headers.get("content-length", "0")) > limit:
                    raise MaterialError("材料超过本次允许的大小，请下载后拆分上传。")
            except ValueError as exc:
                if isinstance(exc, MaterialError):
                    raise
                raise MaterialError("网站返回的材料长度无效。") from exc
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MaterialError("获取材料超时，请重试或直接上传。")
                # read1 does not repeatedly wait for a full chunk on a slow response.
                if connection.sock:
                    connection.sock.settimeout(min(10, remaining))
                elif response.fp:
                    response.fp.raw._sock.settimeout(min(10, remaining))
                chunk = response.read1(min(65536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > limit:
                    raise MaterialError("材料超过本次允许的大小，请下载后拆分上传。")
            if "content-length" in headers and size != int(headers["content-length"]):
                raise MaterialError("材料未能完整下载，请重试或直接上传。")
            return FetchResult(url, b"".join(chunks), headers)
        except (OSError, http.client.HTTPException) as exc:
            raise MaterialError("无法读取公开材料，请稍后重试或直接上传文件。") from exc
        finally:
            connection.close()
    raise MaterialError("论文网站跳转过多，请直接上传文件。")
