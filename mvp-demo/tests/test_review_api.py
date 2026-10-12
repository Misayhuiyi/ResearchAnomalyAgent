import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import job_store


class ReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.runtime=patch.object(app,'RUNTIME_DIR',self.root);self.runtime.start()
        self.scan='abc123abc123';folder=self.root/self.scan;folder.mkdir()
        (folder/'result.json').write_text(json.dumps({'scan_id':self.scan,'source':'sample.csv','scan_status':'partial',
                                                    'findings':[{'id':'FD001','evidence':{}}]}),encoding='utf-8')
        (folder/'report.html').write_text('initial report',encoding='utf-8')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.DemoHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.runtime.stop();self.tmp.cleanup()

    def request(self,path,body=None,origin=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        try:
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
            response=connection.getresponse();data=response.read()
            return response.status,json.loads(data) if 'application/json' in response.getheader('Content-Type','') else data
        finally:connection.close()

    def test_save_conflict_export_and_download(self):
        self.assertEqual(self.request('/api/reviews/'+self.scan)[1]['review']['revision'],0)
        body={'scan_id':self.scan,'finding_id':'FD001','state':'explained','note':'检查说明','revision':0,'request_key':'save-0001'}
        self.assertEqual(self.request('/api/reviews',body)[0],200)
        self.assertEqual(self.request('/api/reviews',body)[1]['review']['revision'],1)
        self.assertEqual(self.request('/api/reviews',{**body,'request_key':'save-0002'})[0],409)
        status,result=self.request('/api/reports',{'scan_id':self.scan,'revision':1,'request_key':'freeze-0001'})
        self.assertEqual(status,200)
        for url in result['report']['downloads'].values():self.assertEqual(self.request(url)[0],200)

    def test_invalid_bodies_and_cross_site_cannot_write(self):
        self.assertEqual(self.request('/api/reviews',{'scan_id':self.scan,'state':[]})[0],400)
        self.assertEqual(self.request('/api/reviews',{'scan_id':'../anything'})[0],404)
        self.assertEqual(self.request('/api/reports',{},'https://example.org')[0],403)

    def test_unfinished_and_cancelled_results_not_reviewable(self):
        (self.root/self.scan/'report.html').unlink()
        self.assertEqual(self.request('/api/reviews/'+self.scan)[0],404)
        (self.root/self.scan/'report.html').write_text('not-final',encoding='utf-8')
        job_store.save(self.root,{'job_id':self.scan,'scan_id':self.scan,'created_at':'test','status':'cancelled'})
        self.assertEqual(self.request('/api/reviews/'+self.scan)[0],404)
        self.assertEqual(self.request('/api/reports',{'scan_id':self.scan,'revision':0,'request_key':'freeze-0001'})[0],404)


if __name__=='__main__':unittest.main()
