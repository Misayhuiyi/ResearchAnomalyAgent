import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import job_store


class CancelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_actual_child_process_stops(self):
        event=threading.Event(); timer=threading.Timer(.25,event.set);timer.start()
        try:
            started=time.monotonic()
            with self.assertRaises(app.ScanCancelled):
                app.run_engine([sys.executable,'-c','import time; time.sleep(30)'],event)
            self.assertLess(time.monotonic()-started,5)
        finally:timer.join()

    def test_queued_cancel_keeps_uploaded_bytes_and_is_not_success(self):
        with patch.object(app.JOB_EXECUTOR,'submit'):
            job=app.start_scan_batch([('source.csv',b'x,y\n1,2\n')],runtime_dir=self.root)
        jid=job['job_id'];self.addCleanup(lambda:app.JOBS.pop(jid,None))
        self.assertEqual(app.cancel_scan_job(jid)['status'],'cancelling')
        app._run_scan_job(jid)
        self.assertEqual(app.get_scan_job(jid,self.root)['status'],'cancelled')
        self.assertEqual((self.root/jid/'submitted'/'source.csv').read_bytes(),b'x,y\n1,2\n')
        self.assertFalse((self.root/jid/'result.json').exists())
        self.assertEqual(app.cancel_scan_job(jid)['status'],'cancelled')

    def test_memory_guard_stops_actual_process_without_fake_result(self):
        with patch.object(app,'ENGINE_RSS_LIMIT',64*1024*1024):
            with self.assertRaisesRegex(app.DemoError,'处理容量'):
                app.run_engine([sys.executable,'-c','import time; data=bytearray(80*1024*1024); time.sleep(20)'])

    def test_cancel_also_stops_spawned_child(self):
        import psutil
        pidfile=self.root/'child.pid'
        program='import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)'
        event=threading.Event();timer=threading.Timer(1,event.set);timer.start()
        try:
            with self.assertRaises(app.ScanCancelled):app.run_engine([sys.executable,'-c',program,str(pidfile)],event)
            self.assertTrue(pidfile.is_file())
            child=int(pidfile.read_text())
            self.assertFalse(psutil.pid_exists(child))
        finally:timer.join()

    def test_completion_race_does_not_undo_cancel(self):
        with patch.object(app.JOB_EXECUTOR,'submit'):
            job=app.start_scan_batch([('source.csv',b'x,y\n1,2\n')],runtime_dir=self.root)
        jid=job['job_id'];self.addCleanup(lambda:app.JOBS.pop(jid,None));self.addCleanup(lambda:app.JOB_CANCEL.pop(jid,None))
        app.cancel_scan_job(jid)
        app._update_job(jid,status='running')
        self.assertEqual(app.get_scan_job(jid,self.root)['status'],'cancelling')
        app._update_job(jid,status='succeeded',result={'secret':'not-final'})
        self.assertEqual(app.get_scan_job(jid,self.root)['status'],'cancelled')
        self.assertIsNone(app.get_scan_job(jid,self.root)['result'])

    def test_restart_does_not_resurrect_cancelling_job(self):
        job_store.save(self.root,{'job_id':'abc123abc123','scan_id':'abc123abc123','created_at':'test','status':'cancelling'})
        app.restore_scan_jobs(self.root)
        self.assertEqual(job_store.get(self.root,'abc123abc123')['status'],'failed')


if __name__=='__main__':unittest.main()
