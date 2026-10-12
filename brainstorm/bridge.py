"""dingtalk-official 消息源桥：钉钉回调（验签）→ room.jsonl；room.jsonl → 群 webhook。

用法：
  python -m brainstorm.bridge [--config path]

入站（红线6）：钉钉开放平台事件订阅推到本服务的 HTTP 回调，
  timestamp+sign 强制验签（HMAC-SHA256 + base64，5 分钟时窗防重放），拒签 401。
出站：扫描房间内 agent 发出的新消息，按 config.local.json 的 webhook token
  发回钉钉群，发送前按 log.redact 关键词脱敏（红线7）。
入站消毒（红线5）：命中注入拦截模式的消息不写入房间，只记日志（block_injection 可关）。

本服务只支持「加签、不加密」的回调安全设置；上线前请用钉钉后台的测试推送核对字段
（可用 --dump 保存原始报文）。
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config as cfgmod
from .room import Room, sanitize

RETRIES = 3


def log(text):
    print("[bridge] %s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), text), flush=True)


def verify_sign(timestamp, sign, secret):
    if not timestamp or not sign or not secret:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    msg = ("%s\n%s" % (timestamp, secret)).encode("utf-8")
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, sign)


def _dig(node, *path):
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def extract_content(ev):
    for path in (("text", "content"), ("data", "text", "content"),
                 ("data", "content"), ("content",), ("message",)):
        val = _dig(ev, *path)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if isinstance(ev.get("text"), str) and ev["text"].strip():
        return ev["text"].strip()
    return ""


def extract_sender(ev):
    for key in ("senderNick", "sender_nick", "senderName", "nick", "sender", "from"):
        val = ev.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    data = ev.get("data")
    if isinstance(data, dict):
        for key in ("senderNick", "sender", "nick"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return "someone"


def send_webhook(token, text, cfg):
    url = "https://oapi.dingtalk.com/robot/send?access_token=" + token
    body = json.dumps({"msgtype": "text",
                       "text": {"content": cfgmod.redact(text, cfg)}})
    last = ""
    for _ in range(RETRIES):
        try:
            req = urllib.request.Request(
                url, data=body.encode("utf-8"),
                headers={"Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=20)
                              .read().decode("utf-8"))
            if resp.get("errcode") == 0:
                return True, ""
            last = str(resp.get("errmsg"))[:120]
        except Exception as exc:
            last = repr(exc)[:120]
        time.sleep(3)
    return False, last


class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.room = Room(cfgmod.room_path(cfg))
        self.secret = cfgmod.local(cfg, "dingtalk", "appSecret") or ""
        self.webhooks = cfgmod.local(cfg, "dingtalk", "webhooks") or {}
        self.agents = {a.get("name") for a in (cfg.get("agents") or [])}
        state_dir = os.path.join(cfg["_dir"], "state")
        os.makedirs(state_dir, exist_ok=True)
        self.out_cursor_path = os.path.join(state_dir, "bridge-out.cursor")

    def out_cursor(self):
        try:
            with open(self.out_cursor_path, "r", encoding="utf-8") as fh:
                return int((fh.read() or "0").strip())
        except (OSError, ValueError):
            return 0

    def save_out_cursor(self, v):
        with open(self.out_cursor_path, "w", encoding="utf-8") as fh:
            fh.write(str(int(v)))

    def handle_callback(self, timestamp, sign, body):
        if not verify_sign(timestamp, sign, self.secret):
            log("验签失败，已拒绝（timestamp=%s）" % timestamp)
            return 401, {"error": "invalid signature"}
        try:
            ev = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except ValueError:
            return 400, {"error": "bad json"}
        content = extract_content(ev)
        sender = extract_sender(ev)
        if not content:
            log("空消息（可能是心跳/确认推送），忽略")
            return 200, {"ok": True}
        if sanitize(content, self.cfg) is None:
            log("消息命中注入拦截，丢弃（sender=%s）" % sender)
            return 200, {"ok": True, "blocked": True}
        who = "human-%s" % sender if sender != "someone" else "human"
        rec = self.room.post(who, content, to="all")
        log("入站 seq=%d from=%s：%s" % (rec["seq"], who, content[:60]))
        return 200, {"ok": True, "seq": rec["seq"]}

    def pump_outgoing(self):
        cursor = self.out_cursor()
        failed = False
        for m in self.room.load():
            if m["seq"] <= cursor:
                continue
            if m.get("from") not in self.agents:
                cursor = m["seq"]
                continue
            token = self.webhooks.get(m["from"]) or self.webhooks.get("default")
            if not token:
                log("no webhook for %s，跳过 seq=%d" % (m.get("from"), m["seq"]))
                cursor = m["seq"]
                continue
            ok, reason = send_webhook(token, m.get("text") or "", self.cfg)
            if ok:
                log("出站 seq=%d → 钉钉 ok" % m["seq"])
            else:
                log("出站 seq=%d 失败：%s" % (m["seq"], reason))
                failed = True
                break
            cursor = m["seq"]
        if cursor != self.out_cursor():
            self.save_out_cursor(cursor)
        return not failed

    def outgoing_loop(self, interval):
        while True:
            try:
                self.pump_outgoing()
            except Exception as exc:
                log("出站扫描失败：%r" % (exc,))
            time.sleep(interval)


def make_handler(bridge, dump_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._reply(200, {"ok": True})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            if dump_path:
                with open(dump_path, "ab") as fh:
                    fh.write((time.strftime("%Y-%m-%d %H:%M:%S") + " "
                              + self.path + "\n").encode("utf-8"))
                    fh.write(body + b"\n\n")
            qs = parse_qs(urlparse(self.path).query)
            ts = (self.headers.get("X-DingTalk-Timestamp")
                  or (qs.get("timestamp") or [""])[0])
            sign = (self.headers.get("X-DingTalk-Signature")
                    or (qs.get("sign") or [""])[0])
            code, obj = bridge.handle_callback(ts, sign, body)
            self._reply(code, obj)

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(prog="brainstorm.bridge")
    ap.add_argument("--config", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--out-interval", type=float, default=3.0)
    ap.add_argument("--dump", action="store_true",
                    help="保存回调原始报文到 bridge-callback.dump 便于对接")
    a = ap.parse_args(argv)

    cfg = cfgmod.load_config(a.config)
    src = next((s for s in (cfg.get("sources") or [])
                if s.get("type") == "dingtalk-official" and s.get("enabled")), None)
    if not src:
        sys.exit("config.sources 里没有 enabled 的 dingtalk-official 源")
    if not cfgmod.local(cfg, "dingtalk", "appSecret"):
        sys.exit("config.local.json 缺 dingtalk.appSecret（验签必需）")

    host = a.host or src.get("host") or "127.0.0.1"
    port = a.port or src.get("port") or 8080
    dump_path = (os.path.join(cfg["_dir"], "bridge-callback.dump")
                 if a.dump else None)
    bridge = Bridge(cfg)

    threading.Thread(target=bridge.outgoing_loop,
                     args=(a.out_interval,), daemon=True).start()
    handler = make_handler(bridge, dump_path)
    server = ThreadingHTTPServer((host, port), handler)
    log("回调服务 http://%s:%d/ （验签=appSecret，出站间隔 %.0fs）"
        % (host, port, a.out_interval))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
