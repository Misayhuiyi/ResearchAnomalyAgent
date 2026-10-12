import copy
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from platform_ports import Actor, LOCAL_ACTOR
from review_store import ReviewStore, ReviewError, Conflict, Unavailable


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ReviewStore(Path(self.tmp.name))
        self.result = {'scan_id': 'abcd1234abcd', 'source': '原始.csv', 'findings': [{'id': 'FD001'}]}
        self.store.register(LOCAL_ACTOR, self.result)

    def save(self, **kwargs):
        args = dict(actor=LOCAL_ACTOR, scan=self.result['scan_id'], finding='FD001',
                    state='explained', note='单位换算，有原始记录。', expected=0, key='request-0001')
        args.update(kwargs)
        return self.store.save(**args)

    def test_restart_audit_and_immutable_source(self):
        before = copy.deepcopy(self.result)
        self.assertEqual(self.save()['revision'], 1)
        reopened = ReviewStore(Path(self.tmp.name))
        self.assertEqual(reopened.view(LOCAL_ACTOR, before['scan_id'])['reviews']['FD001']['state'], 'explained')
        self.assertEqual(reopened.history(LOCAL_ACTOR, before['scan_id'])[0]['before']['state'], 'pending')
        self.assertEqual(before, self.result)
        changed = copy.deepcopy(before)
        changed['findings'][0]['id'] = 'other'
        with self.assertRaises(Conflict):
            reopened.register(LOCAL_ACTOR, changed)

    def test_validation_and_owner(self):
        for change in [{'note': ''}, {'note': '  '}, {'note': 'a'*2001}, {'state': 'fraud'},
                       {'finding': 'unknown'}, {'expected': True}, {'key': '../escape'}]:
            with self.subTest(change=change), self.assertRaises(ReviewError):
                self.save(**change)
        for actor in [Actor('other', 'single-user'), Actor('local', 'other')]:
            with self.assertRaises(Unavailable): self.save(actor=actor)
            with self.assertRaises(Unavailable): self.store.register(actor, self.result)

    def test_replay_and_stale(self):
        first = self.save()
        self.assertEqual(first, self.save())
        with self.assertRaises(Conflict): self.save(note='changed')
        with self.assertRaises(Conflict): self.save(key='another-key')
        self.assertEqual(len(self.store.history(LOCAL_ACTOR, self.result['scan_id'])), 1)

    def test_concurrent_only_one_revision(self):
        def attempt(i):
            try: return self.save(key=f'request-{i:04}')['revision']
            except Conflict: return 'conflict'
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attempt, [1, 2]))
        self.assertEqual(sorted(map(str, results)), ['1', 'conflict'])

    def test_freeze_replay_does_not_follow_later_review(self):
        scan = self.result['scan_id']
        original = self.store.freeze(LOCAL_ACTOR, scan, 0, 'freeze-0001')
        self.save()
        same = self.store.freeze(LOCAL_ACTOR, scan, 0, 'freeze-0001')
        self.assertEqual(original, same)
        self.assertEqual(same['review']['reviews'], {})
        self.assertFalse(same['ready'])
        new = self.store.freeze(LOCAL_ACTOR, scan, 1, 'freeze-0002')
        self.assertNotEqual(original['snapshot_hash'], new['snapshot_hash'])
        with self.assertRaises(Unavailable): self.store.snapshot(Actor('x','x'), new['report_id'])
        self.store.mark_ready(LOCAL_ACTOR, new['report_id'])
        self.assertTrue(self.store.snapshot(LOCAL_ACTOR, new['report_id'])['ready'])
        self.assertEqual(len(self.store.reports(LOCAL_ACTOR, scan)), 2)


if __name__ == '__main__': unittest.main()
