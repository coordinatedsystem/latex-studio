"""Wire-format tests against loopback only. No external services or real credentials."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from urllib.parse import parse_qs

from studio_ai import request_json


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                cls.seen.append({'path':self.path,'headers':dict(self.headers),'body':body})
                if self.path=='/redirect':
                    self.send_response(307);self.send_header('Location','http://127.0.0.1:'+str(self.server.server_port)+'/should-not-run');self.end_headers();return
                if self.path=='/limited':
                    self.send_response(429);self.end_headers();self.wfile.write(b'secret-from-server-body');return
                self.send_response(200);self.end_headers()
                self.wfile.write(b'<html>not-json</html>' if self.path=='/html' else json.dumps({'ok':True}).encode())
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def test_json_and_form_reach_loopback_with_correct_encoding(self):
        result=request_json(self.base+'/json',{'text':'独立样例','messages':[]},{'Authorization':'Bearer fake-test-only'})
        self.assertTrue(result['ok'])
        self.assertEqual(json.loads(self.seen[-1]['body'])['text'],'独立样例')
        self.assertEqual(self.seen[-1]['headers']['Authorization'],'Bearer fake-test-only')
        request_json(self.base+'/form',{'q':'你好 + world','signType':'v3'},form=True)
        form=parse_qs(self.seen[-1]['body'].decode())
        self.assertEqual(form['q'],['你好 + world'])
        self.assertEqual(self.seen[-1]['headers']['Content-Type'],'application/x-www-form-urlencoded')

    def test_redirect_never_forwards_credentials(self):
        start=len(self.seen)
        with self.assertRaisesRegex(ValueError,'重定向'):
            request_json(self.base+'/redirect',{'text':'sample'},{'Authorization':'Bearer fake-test-only'})
        self.assertEqual(len(self.seen),start+1)

    def test_error_does_not_echo_remote_body(self):
        with self.assertRaises(ValueError) as caught:
            request_json(self.base+'/limited',{'text':'sample'})
        self.assertIn('429',str(caught.exception))
        self.assertNotIn('secret-from-server-body',str(caught.exception))

    def test_html_response_is_not_reported_as_ai_success(self):
        with self.assertRaisesRegex(ValueError,'JSON'):
            request_json(self.base+'/html',{'text':'sample'})


if __name__=='__main__':
    unittest.main()
