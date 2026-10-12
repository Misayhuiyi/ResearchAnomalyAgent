"""Owner-scoped review journal and immutable report snapshots.

The local HTTP adapter is single-user; platform adapters must supply a verified Actor.
Source results are never edited by a review. SQLite serializes concurrent revisions.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from platform_ports import Actor

STATES = {'pending': '待复核', 'explained': '已有合理解释', 'further_check': '需要进一步核查'}


class ReviewError(ValueError):
    status = 400


class Conflict(ReviewError):
    status = 409


class Unavailable(ReviewError):
    status = 404


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class ReviewStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS scans (
                  id TEXT PRIMARY KEY, tenant TEXT NOT NULL, owner TEXT NOT NULL,
                  source TEXT NOT NULL, source_hash TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reviews (
                  scan TEXT, finding TEXT, state TEXT, note TEXT, changed TEXT,
                  PRIMARY KEY(scan, finding));
                CREATE TABLE IF NOT EXISTS events (
                  scan TEXT, revision INTEGER, event TEXT, PRIMARY KEY(scan, revision));
                CREATE TABLE IF NOT EXISTS requests (
                  scan TEXT, key TEXT, signature TEXT, response TEXT, PRIMARY KEY(scan, key));
                CREATE TABLE IF NOT EXISTS snapshots (
                  id TEXT PRIMARY KEY, scan TEXT, revision INTEGER, body TEXT, hash TEXT,
                  ready INTEGER NOT NULL DEFAULT 0);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'reviews.sqlite3', timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _scan(db, actor, scan):
        row = db.execute('SELECT * FROM scans WHERE id=? AND tenant=? AND owner=?',
                         (scan, actor.tenant, actor.subject)).fetchone()
        if not row:
            raise Unavailable('该检查记录不存在或无权查看。')
        return row

    def register(self, actor: Actor, result: dict):
        scan = result.get('scan_id')
        if not isinstance(scan, str) or not re.fullmatch(r'[a-f0-9]{12}', scan):
            raise ReviewError('检查编号无效。')
        findings = result.get('findings', [])
        ids = [item.get('id') for item in findings]
        if any(not isinstance(key, str) or not key for key in ids) or len(set(ids)) != len(ids):
            raise ReviewError('检查项目编号重复或缺失，不能保存复核。')
        source, sha = encode(result), digest(result)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM scans WHERE id=?', (scan,)).fetchone()
            if row:
                self._scan(db, actor, scan)
                if row['source_hash'] != sha:
                    raise Conflict('原检查结果已变化，请创建新检查记录。')
            else:
                db.execute('INSERT INTO scans(id,tenant,owner,source,source_hash) VALUES(?,?,?,?,?)',
                           (scan, actor.tenant, actor.subject, source, sha))

    @staticmethod
    def _view(db, row):
        reviews = {r['finding']: {'state': r['state'], 'note': r['note'], 'changed_at': r['changed']}
                   for r in db.execute('SELECT * FROM reviews WHERE scan=?', (row['id'],))}
        return {'scan_id': row['id'], 'revision': row['revision'], 'source_hash': row['source_hash'],
                'reviews': reviews}

    def view(self, actor, scan):
        with self.connect() as db:
            db.execute('BEGIN')
            return self._view(db, self._scan(db, actor, scan))

    @staticmethod
    def _request(db, scan, key, signature):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key):
            raise ReviewError('保存凭据无效，请刷新后重试。')
        saved = db.execute('SELECT * FROM requests WHERE scan=? AND key=?', (scan, key)).fetchone()
        if saved:
            if saved['signature'] != signature:
                raise Conflict('同一次操作的内容已变化，请重新提交。')
            return json.loads(saved['response'])

    @staticmethod
    def _revision(expected, actual):
        if type(expected) is not int or expected < 0:
            raise ReviewError('复核版本无效。')
        if expected != actual:
            raise Conflict('这份记录已在其他页面更新，请刷新复核记录后重新提交。')

    def save(self, actor, scan, finding, state, note, expected, key):
        if not isinstance(state, str) or state not in STATES or not isinstance(note, str) or len(note) > 2000:
            raise ReviewError('请选择复核状态，说明不超过 2000 字。')
        if not isinstance(finding, str):
            raise ReviewError('待核对项编号无效。')
        note = note.strip()
        if state == 'explained' and not note:
            raise ReviewError('请填写合理解释的依据。')
        signature = digest(['review', finding, state, note, expected])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._scan(db, actor, scan)
            replay = self._request(db, scan, key, signature)
            if replay is not None:
                return replay
            self._revision(expected, row['revision'])
            if finding not in {f['id'] for f in json.loads(row['source']).get('findings', [])}:
                raise ReviewError('该待核对项不属于本次检查。')
            before = self._view(db, row)['reviews'].get(finding, {'state': 'pending', 'note': ''})
            changed = now()
            after = {'state': state, 'note': note, 'changed_at': changed}
            revision = row['revision'] + 1
            db.execute('INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?)', (scan, finding, state, note, changed))
            db.execute('UPDATE scans SET revision=? WHERE id=?', (revision, scan))
            event = {'finding': finding, 'before': before, 'after': after, 'operator': actor.subject,
                     'tenant': actor.tenant, 'revision': revision, 'at': changed}
            db.execute('INSERT INTO events VALUES(?,?,?)', (scan, revision, encode(event)))
            answer = self._view(db, self._scan(db, actor, scan))
            db.execute('INSERT INTO requests VALUES(?,?,?,?)', (scan, key, signature, encode(answer)))
            return answer

    def history(self, actor, scan):
        with self.connect() as db:
            self._scan(db, actor, scan)
            return [json.loads(row['event']) for row in db.execute(
                'SELECT event FROM events WHERE scan=? ORDER BY revision', (scan,))]

    def freeze(self, actor, scan, expected, key, content_review=None):
        signature = digest(['freeze', expected, content_review])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._scan(db, actor, scan)
            replay = self._request(db, scan, key, signature)
            if replay is not None:
                return self._snapshot(db, actor, replay['report_id'])
            self._revision(expected, row['revision'])
            report_id = uuid.uuid4().hex
            view = self._view(db, row)
            snapshot = {'report_id': report_id, 'scan_id': scan, 'revision': row['revision'],
                        'created_at': now(), 'source_hash': row['source_hash'],
                        'result': json.loads(row['source']), 'review': view,
                        'history': [json.loads(r['event']) for r in db.execute(
                            'SELECT event FROM events WHERE scan=? ORDER BY revision', (scan,))]}
            sha = digest(snapshot)
            if content_review is not None:
                snapshot['content_review'] = content_review
                sha = digest(snapshot)
            db.execute('INSERT INTO snapshots(id,scan,revision,body,hash) VALUES(?,?,?,?,?)',
                       (report_id, scan, row['revision'], encode(snapshot), sha))
            db.execute('INSERT INTO requests VALUES(?,?,?,?)', (scan, key, signature, encode({'report_id': report_id})))
            return {**snapshot, 'snapshot_hash': sha, 'ready': False}

    def _snapshot(self, db, actor, report_id):
        row = db.execute('SELECT * FROM snapshots WHERE id=?', (report_id,)).fetchone()
        if not row:
            raise Unavailable('报告不存在或无权查看。')
        self._scan(db, actor, row['scan'])
        body = json.loads(row['body'])
        if digest(body) != row['hash']:
            raise Conflict('报告记录校验未通过，暂不能下载。')
        return {**body, 'snapshot_hash': row['hash'], 'ready': bool(row['ready'])}

    def snapshot(self, actor, report_id):
        with self.connect() as db:
            return self._snapshot(db, actor, report_id)

    def mark_ready(self, actor, report_id):
        with self.connect() as db:
            self._snapshot(db, actor, report_id)
            db.execute('UPDATE snapshots SET ready=1 WHERE id=?', (report_id,))

    def reports(self, actor, scan):
        with self.connect() as db:
            self._scan(db, actor, scan)
            return [{'report_id': row['id'], 'revision': row['revision'], 'ready': bool(row['ready']),
                     'created_at': json.loads(row['body'])['created_at']} for row in db.execute(
                         'SELECT * FROM snapshots WHERE scan=? ORDER BY rowid DESC LIMIT 100', (scan,))]
