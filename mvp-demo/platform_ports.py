"""Application-owned platform contracts, not invented Baiyin endpoint definitions."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from public_fetch import MaterialError


@dataclass(frozen=True)
class Actor:
    tenant: str
    subject: str


class IdentityPort(Protocol):
    def authenticate(self, credential: str) -> Actor:
        """Verify with platform; never trust a user ID supplied by the browser."""
        ...


class MaterialStorePort(Protocol):
    def save(self, actor: Actor, filename: str, content: bytes, provenance: dict) -> dict: ...
    def load(self, actor: Actor, material_id: str) -> tuple[dict, bytes]: ...


class TaskPort(Protocol):
    def submit(self, actor: Actor, material_ids: list[str], idempotency_key: str) -> str: ...
    def status(self, actor: Actor, task_id: str) -> dict: ...
    def cancel(self, actor: Actor, task_id: str) -> None: ...


# Deliberately not an authentication implementation. Only valid on the local loopback server.
LOCAL_ACTOR = Actor("local", "single-user")
STORE_LOCK = threading.Lock()


class LocalMaterialStore:
    """Staging snapshots; metadata goes last so interrupted imports cannot be loaded."""
    def __init__(self, root: Path, max_bytes: int = 500 * 1024 * 1024, max_items: int = 100):
        self.root, self.max_bytes, self.max_items = Path(root), max_bytes, max_items

    def save(self, actor: Actor, filename: str, content: bytes, provenance: dict) -> dict:
        sha = hashlib.sha256(content).hexdigest()
        identity = json.dumps([actor.tenant, actor.subject, filename, provenance.get("source_url"), sha], ensure_ascii=False)
        material_id = hashlib.sha256(identity.encode()).hexdigest()[:32]
        metadata = {"source_id": material_id, "filename": filename, "size": len(content), "sha256": sha,
                    "owner": {"tenant": actor.tenant, "subject": actor.subject}, "provenance": provenance}
        with STORE_LOCK:
            self.root.mkdir(parents=True, exist_ok=True)
            folder = self.root / material_id
            if (folder / "source.json").is_file():
                return self.load(actor, material_id)[0]
            # Includes incomplete content files, so interrupted writes cannot bypass the quota.
            contents = list(self.root.glob("*/content"))
            if len(contents) >= self.max_items or sum(path.stat().st_size for path in contents) + len(content) > self.max_bytes:
                raise MaterialError("本机已获取的材料较多，请联系管理员整理后重试；也可直接上传。")
            folder.mkdir(exist_ok=True)
            (folder / "content").write_bytes(content)
            pending = folder / "source.pending"
            pending.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
            pending.replace(folder / "source.json")
        return metadata

    def load(self, actor: Actor, material_id: str) -> tuple[dict, bytes]:
        if not isinstance(material_id, str) or not re.fullmatch(r"[a-f0-9]{32}", material_id):
            raise MaterialError("材料编号无效，请重新获取。")
        try:
            folder = self.root / material_id
            metadata = json.loads((folder / "source.json").read_text(encoding="utf-8"))
            if metadata.get("owner") != {"tenant": actor.tenant, "subject": actor.subject}:
                raise MaterialError("该材料不存在或无权读取。")
            size = (folder / "content").stat().st_size
            if size != metadata.get("size") or size > 20 * 1024 * 1024:
                raise MaterialError("材料已发生变化，请重新获取。")
            content = (folder / "content").read_bytes()
            if hashlib.sha256(content).hexdigest() != metadata.get("sha256"):
                raise MaterialError("材料已发生变化，请重新获取。")
            return metadata, content
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, MaterialError):
                raise
            raise MaterialError("材料无法读取，请重新获取。") from exc
