import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import job_store


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.executor=patch.object(app.JOB_EXECUTOR,'submit');self.mock=self.executor.start();self.addCleanup(self.executor.stop)
        self.addCleanup(app.JOBS.clear);self.addCleanup(app.JOB_CANCEL.clear)

    def start(self,files,key,parent=None):
        return app.start_scan_batch(files,runtime_dir=self.root,request_key=key,parent_scan=parent)

    def finish(self,job,state='succeeded'):
        saved=job_store.get(self.root,job['job_id']);saved['status']=state;job_store.save(self.root,saved)
        app.JOBS[job['job_id']]['status']=state

    def test_idempotent_same_submission_and_reject_changed_content(self):
        files=[('data.csv',b'a,b\n1,2\n')]
        one=self.start(files,'submit-0001');two=self.start(files,'submit-0001')
        self.assertEqual(one['job_id'],two['job_id']);self.mock.assert_called_once()
        with self.assertRaises(app.DemoError):self.start([('data.csv',b'a,b\n2,3\n')],'submit-0001')
        app.JOBS.clear()
        self.assertEqual(self.start(files,'submit-0001')['job_id'],one['job_id'])

    def test_new_version_preserves_original_and_retains_other_materials(self):
        original=b'a,b\n1,2\n'
        parent=self.start([('data.csv',original),('other.csv',b'a,b\n3,4\n')],'submit-0001');self.finish(parent)
        changed=b'a,b\n4,5\n'
        child=self.start([('data.csv',changed)],'submit-0002',parent['job_id'])
        self.assertEqual(child['paper_id'],parent['job_id']);self.assertEqual(child['material_version'],2)
        self.assertEqual(child['parent_scan'],parent['job_id'])
        self.assertEqual((self.root/parent['job_id']/'submitted'/'data.csv').read_bytes(),original)
        self.assertEqual((self.root/child['job_id']/'submitted'/'data.csv').read_bytes(),changed)
        self.assertTrue((self.root/child['job_id']/'submitted'/'other.csv').exists())
        self.assertEqual(len(job_store.family(self.root,parent['job_id'])),2)

    def test_retry_retains_snapshot_and_rejects_running_or_corrupt_parent(self):
        files=[('data.csv',b'a,b\n1,2\n')]
        parent=self.start(files,'submit-0001')
        with self.assertRaises(app.DemoError):self.start([],'submit-0002',parent['job_id'])
        self.finish(parent,'failed')
        child=self.start([],'submit-0002',parent['job_id'])
        self.assertEqual(child['input_hashes'],parent['input_hashes'])
        (self.root/parent['job_id']/'submitted'/'data.csv').write_bytes(b'changed')
        with self.assertRaises(app.DemoError):self.start([],'submit-0003',parent['job_id'])

    def test_replacement_does_not_reuse_old_url_provenance(self):
        parent=app.start_scan_batch([('data.csv',b'a,b\n1,2\n')],runtime_dir=self.root,
            material_sources=[{'filename':'data.csv','source_url':'https://example.org/old.csv'}])
        self.finish(parent)
        child=self.start([('data.csv',b'a,b\n3,4\n')],'submit-0002',parent['job_id'])
        self.assertEqual(job_store.get(self.root,child['job_id'])['material_sources'],[])

    def test_queue_limit_does_not_reject_idempotent_existing_submission(self):
        files=[('data.csv',b'a,b\n1,2\n')]
        for i in range(4):self.start(files,f'submit-000{i}')
        with self.assertRaises(app.DemoError):self.start(files,'submit-0004')
        self.assertEqual(self.start(files,'submit-0000')['status'],'queued')


if __name__=='__main__':unittest.main()
