#!/usr/bin/env python3
"""Bounded subprocess/fake-TCP proof for the devtools bridge."""
from __future__ import annotations
import json
from http.client import HTTPConnection
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from scripts.harness.kpharness.devtools_bridge import Bridge, BridgeError, MAX_BODY, WEB_ROOT
from scripts.harness.kpharness.client import ChannelTimeout

class FakeHarness:
    def __init__(self, drop_submit=False):
        self.drop_submit=drop_submit
        self.lines=[]; self.stop=threading.Event(); self.sock=socket.socket(); self.sock.bind(("127.0.0.1",0)); self.sock.listen(1); self.port=self.sock.getsockname()[1]
        self.thread=threading.Thread(target=self.run,daemon=True); self.thread.start()
    def result(self,op):
        base={"protocol":"kp.console.v1","runtime":"runtime-a"}; ident={"session":"18446744073709551615"}
        if op=="status": return {**base,"status":"Found",**ident,"submitted":"9","last_line":"12"}
        if op=="submit": return {**base,"status":"None",**ident,"request":"18446744073709551615"}
        if op=="outcome": return {**base,"status":"Found","outcome":{**ident,"request":"18446744073709551615","state":"Succeeded","values":[{"type":"String","bytes":{"encoding":"base64","data":"AP8A","byte_length":"3"},"original_bytes":"3","truncated":False}],"error":None}}
        if op=="output": return {**base,"status":"Found",**ident,"dropped_through":"12","lines":[{**ident,"request":"18446744073709551615","text":{"encoding":"base64","data":"AP8A","byte_length":"3"}}]}
        if op=="cancel": return {**base,"status":"Requested"}
        return {**base,"status":"Found","names":[]}
    def run(self):
        try:
            conn,_=self.sock.accept(); conn.settimeout(2); buf=b""
            with conn:
                while not self.stop.is_set():
                    try: chunk=conn.recv(65536)
                    except socket.timeout: continue
                    if not chunk: return
                    buf+=chunk
                    while b"\n" in buf:
                        raw,buf=buf.split(b"\n",1)
                        if not raw: continue
                        req=json.loads(raw); self.lines.append(req)
                        if self.drop_submit and req.get("op") == "submit": return
                        out={"id":req["id"],"ok":True,"result":self.result(req.get("op"))}; conn.sendall((json.dumps(out)+"\n").encode())
        except (OSError,json.JSONDecodeError): return
    def close(self): self.stop.set(); self.sock.close(); self.thread.join(timeout=2)

class BridgeSubprocessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream=FakeHarness(); cls.tmp=tempfile.TemporaryDirectory(prefix="kp-bridge-"); cls.token_path=Path(cls.tmp.name)/"token"
        env=dict(os.environ,PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE="1")
        cls.proc=subprocess.Popen(["python3","-m","scripts.harness.kpharness.devtools_bridge","--standalone","--port",str(cls.upstream.port),"--listen","127.0.0.1:0","--token-file",str(cls.token_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        url=cls.proc.stdout.readline().strip(); cls.proc.stdout.readline(); cls.port=int(url.rsplit(":",1)[1].rstrip("/")); cls.host=f"127.0.0.1:{cls.port}"; cls.token=cls.token_path.read_text().strip()
        cls.stdout_lines = [url]
    @classmethod
    def tearDownClass(cls): cls.proc.terminate(); cls.proc.wait(timeout=3); cls.upstream.close(); cls.tmp.cleanup()
    @classmethod
    def http(cls,method,path,body=None,*,token=None,origin=True,host=None):
        c=HTTPConnection("127.0.0.1",cls.port,timeout=2); headers={"Host":host or cls.host}
        if origin: headers["Origin"]=f"http://{cls.host}"
        if token is not None: headers["Authorization"]="Bearer "+token
        if body is not None: headers["Content-Type"]="application/json"
        c.request(method,path,json.dumps(body) if body is not None else None,headers); r=c.getresponse(); data=r.read(); c.close(); return r.status,data
    def test_page_bootstrap_and_manifest(self):
        status,page=self.http("GET","/"); self.assertEqual(status,200); self.assertIn(b"kotor-console.mjs",page)
        status,_=self.http("GET","/../MANIFEST"); self.assertEqual(status,404)
        self.assertNotIn(self.token.encode(), page); self.assertEqual(self.token_path.stat().st_mode & 0o777, 0o600)
    def test_auth_path_origin_reserved(self):
        before=len(self.upstream.lines); self.assertEqual(self.http("POST","/v1/console",{"op":"status"})[0],401)
        self.assertEqual(self.http("POST","/wrong",{"op":"status"},token=self.token)[0],404)
        self.assertEqual(self.http("POST","/v1/console",{"op":"status","timeout":1},token=self.token)[0],400)
        self.assertEqual(self.http("POST","/v1/console",{"op":"status"},token=self.token,origin=False)[0],403); self.assertEqual(len(self.upstream.lines),before)
    def test_guard_matrix_and_body_budget(self):
        before = len(self.upstream.lines)
        for kwargs, expected in [
            ({"token": "wrong"}, 401),
            ({"token": self.token, "origin": False}, 403),
            ({"token": self.token, "host": "localhost:" + str(self.port)}, 400),
            ({"token": self.token, "host": "attacker.example"}, 400),
        ]:
            self.assertEqual(self.http("POST", "/v1/console", {"op": "status"}, **kwargs)[0], expected)
        for body in ({"op": "reset"}, {"op": "status", "cmd": "load_save"}, {"op": "status", "protocol": "x"}, {"op": "status", "self": {}}):
            self.assertEqual(self.http("POST", "/v1/console", body, token=self.token)[0], 400)
        self.assertEqual(self.http("POST", "/v1/console", {"op": "submit", "code": "x" * MAX_BODY}, token=self.token)[0], 413)
        for method in ("OPTIONS", "POST"):
            c = HTTPConnection("127.0.0.1", self.port, timeout=2)
            c.request(method, "/v1/console", "{}", {"Host": self.host, "Origin": "http://attacker.example", "Authorization": "Bearer " + self.token})
            r = c.getresponse()
            self.assertEqual(r.status, 403)
            self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))
            r.read(); c.close()
        self.assertEqual(len(self.upstream.lines), before)
        for path in ("/%2e%2e/MANIFEST", "/MANIFEST", "/kotor-console.test.mjs"):
            self.assertEqual(self.http("GET", path)[0], 404)
        # Every native-legal source byte may need JSON escaping.
        self.assertEqual(self.http("POST", "/v1/console", {"op": "submit", "code": "\x00" * 16384}, token=self.token)[0], 200)

    def test_nonloopback_start_refused(self):
        with tempfile.TemporaryDirectory() as root:
            proc = subprocess.run(["python3", "-m", "scripts.harness.kpharness.devtools_bridge", "--standalone", "--listen", "0.0.0.0:0", "--token-file", str(Path(root)/"token")], text=True, capture_output=True, timeout=5)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("127.0.0.1", proc.stderr)

    def test_wire_identity_ids_bytes_and_cancel(self):
        status,data=self.http("POST","/v1/console",{"op":"status"},token=self.token); self.assertEqual(status,200); ident=json.loads(data); identity={"runtime":ident["runtime"],"session":ident["session"]}
        status,data=self.http("POST","/v1/console",{"op":"submit",**identity,"code":"return 1"},token=self.token); submitted=json.loads(data); self.assertEqual(submitted["request"],"18446744073709551615")
        status,data=self.http("POST","/v1/console",{"op":"outcome",**identity,"request":submitted["request"]},token=self.token); outcome=json.loads(data)["outcome"]; self.assertEqual(outcome["session"],identity["session"]); self.assertEqual(outcome["request"],submitted["request"]); self.assertEqual(outcome["values"][0]["bytes"]["data"],"AP8A")
        status,data=self.http("POST","/v1/console",{"op":"cancel",**identity,"request":submitted["request"]},token=self.token); self.assertEqual(json.loads(data)["status"],"Requested")
        self.assertTrue(all(x["cmd"]=="devtools" and x["protocol"]=="kp.console.v1" for x in self.upstream.lines))
    def test_invalid_commands_and_noncanonical_op(self):
        self.assertEqual(self.http("POST","/v1/console",{"cmd":"lua","op":"status"},token=self.token)[0],400)
        self.assertEqual(self.http("POST","/v1/console",{"op":["status"]},token=self.token)[0],400)

    def test_upstream_tcp_drop_is_not_replayed(self):
        upstream = FakeHarness(drop_submit=True)
        proc = None
        try:
            with tempfile.TemporaryDirectory() as root:
                token_path = Path(root) / "token"
                proc = subprocess.Popen(["python3", "-m", "scripts.harness.kpharness.devtools_bridge", "--standalone", "--port", str(upstream.port), "--token-file", str(token_path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                url = proc.stdout.readline().strip()
                token_line = proc.stdout.readline()
                port = int(url.rsplit(":", 1)[1].rstrip("/"))
                token = token_path.read_text().strip()
                for _ in range(2):
                    conn = HTTPConnection("127.0.0.1", port, timeout=3)
                    conn.request("POST", "/v1/console", json.dumps({"op":"submit", "runtime":"r", "session":"1", "code":"mutate()"}), {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}", "Authorization": "Bearer " + token})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 502)
                    self.assertIn(b"upstream_lost", response.read())
                    conn.close()
                self.assertEqual(sum(r.get("op") == "submit" for r in upstream.lines), 1)
                proc.terminate()
                stdout, stderr = proc.communicate(timeout=3)
                self.assertNotIn(token, url + token_line + stdout + stderr)
        finally:
            if proc and proc.poll() is None:
                proc.terminate(); proc.wait(timeout=3)
            upstream.close()

    def test_busy_startup_exits_before_serving(self):
        sock=socket.socket(); sock.bind(("127.0.0.1",0)); sock.listen(1); port=sock.getsockname()[1]
        def refuse():
            try:
                conn,_=sock.accept(); conn.recv(4096); conn.sendall(b'{"ok":false,"error":"busy: another client is connected"}\n'); conn.close()
            finally: sock.close()
        threading.Thread(target=refuse,daemon=True).start()
        with tempfile.TemporaryDirectory() as root:
            env=dict(os.environ,PYTHONPATH=str(Path.cwd()),PYTHONDONTWRITEBYTECODE="1")
            proc=subprocess.run(["python3","-m","scripts.harness.kpharness.devtools_bridge","--standalone","--port",str(port),"--listen","127.0.0.1:0","--token-file",str(Path(root)/"token")],env=env,text=True,capture_output=True,timeout=5)
        self.assertNotEqual(proc.returncode,0); self.assertIn("busy: another client is connected",proc.stderr)

class BridgeUnitTest(unittest.TestCase):
    def test_timeout_closes_and_never_replays(self):
        class Timeout:
            def __init__(self): self.calls=0; self.closed=0
            def request(self,*a,**k): self.calls+=1; raise ChannelTimeout("hung")
            def close(self): self.closed+=1
        ch=Timeout(); bridge=Bridge(ch,"a"*64)
        with self.assertRaisesRegex(BridgeError,"upstream_lost"): bridge.forward({"op":"status"})
        with self.assertRaisesRegex(BridgeError,"upstream_lost"): bridge.forward({"op":"status"})
        self.assertEqual((ch.calls,ch.closed),(1,1))
    def test_publication_exact_staged_files(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            for name in (WEB_ROOT / "MANIFEST").read_text().splitlines():
                (p / name).write_bytes((WEB_ROOT / name).read_bytes())
            Bridge.validate_publication(p)
            for name in ("leak.bif", "leak.tga", "MANIFEST"):
                extra = p / name
                extra.write_text("leak.bif\n")
                with self.assertRaisesRegex(BridgeError, "allowlist mismatch"):
                    Bridge.validate_publication(p)
                extra.unlink()
            (p / "index.html").unlink()
            (p / "index.html").symlink_to(WEB_ROOT / "index.html")
            with self.assertRaisesRegex(BridgeError, "symlinks"):
                Bridge.validate_publication(p)

    def test_queued_calls_never_send_after_upstream_loss(self):
        class Ch:
            def __init__(self):
                self.calls = 0
                self.entered = threading.Event()
                self.release = threading.Event()
            def request(self, *args, **kwargs):
                self.calls += 1
                self.entered.set()
                self.release.wait(2)
                raise ChannelTimeout("lost")
            def close(self): pass
        ch = Ch()
        bridge = Bridge(ch, "a" * 64)
        errors = []
        def forward():
            try: bridge.forward({"op": "submit", "code": "mutate()"})
            except BridgeError as error: errors.append(str(error))
        first = threading.Thread(target=forward)
        first.start()
        self.assertTrue(ch.entered.wait(1))
        second = threading.Thread(target=forward)
        second.start()
        # Hold the active call while the second caller reaches the queue.
        time.sleep(0.05)
        ch.release.set()
        first.join(2); second.join(2)
        self.assertEqual(len(errors), 2)
        self.assertEqual(ch.calls, 1)

    def test_queue_bound_and_manifest_allowlist(self):
        class Ch:
            def __init__(self): self.calls=0; self.release=threading.Event()
            def request(self,*a,**k): self.calls+=1; self.release.wait(2); return {"protocol":"kp.console.v1","runtime":"r"}
        ch=Ch(); bridge=Bridge(ch,"a"*64); threads=[threading.Thread(target=lambda: bridge.forward({"op":"status"})) for _ in range(16)]
        for t in threads: t.start()
        time.sleep(0.2)
        with self.assertRaisesRegex(BridgeError,"queue full"): bridge.forward({"op":"status"})
        ch.release.set()
        for t in threads: t.join(2)
        with tempfile.TemporaryDirectory() as root:
            p=Path(root); (p/"MANIFEST").write_text("index.html\n"); (p/"index.html").write_text("ok"); (p/"leak.bif").write_bytes(b"x")
            b=Bridge(Ch(),"a"*64,web_root=p)
            self.assertEqual(b.static("/")[0],b"ok")
            with self.assertRaises(FileNotFoundError): b.static("/leak.bif")
            with self.assertRaisesRegex(BridgeError,"allowlist mismatch"): b.validate_publication(p)

if __name__=="__main__": unittest.main()
