import http.server
import ssl
import json
import threading
import sys
import os

SCRATCH_DIR = os.path.dirname(os.path.abspath(__file__))
FIXED_STORE_PATH = os.path.join(SCRATCH_DIR, "store_v2_fixed.json")

with open(FIXED_STORE_PATH, "r") as f:
    FIXED_STORE_DATA = f.read().encode("utf-8")

DEVICE_CONFIG = json.dumps({
    "configName": "benchmark Config",
    "ignoreMe": False,
    "models": [],
    "scale": -1,
    "deviceSpeed": 4,
    "enableTextureCompression": True,
    "enableVHSFX": True,
    "enableResolutionLimitation": True
}).encode("utf-8")

HOUSTON_CONFIG = json.dumps({
    "ads_config": "http://172.20.224.1/ads/",
    "amazon_receipt_validation": "http://172.20.224.1/partners/amazon/",
    "apple_receipt_validation": "http://172.20.224.1/partners/apple/",
    "crosspromo_server_url": "http://172.20.224.1",
    "dlc_check": "http://172.20.224.1/check_dlc.php",
    "dynamic_download": "http://172.20.224.1/",
    "flurry_reward_check": "http://172.20.224.1/partners/flurry/",
    "game_session": "http://172.20.224.1/gamesession/",
    "google_receipt_validation": "http://172.20.224.1/partners/google/",
    "houston_api": "http://172.20.224.1/api/",
    "houston_leaderboard": "http://172.20.224.1/leaderboard/",
    "inapp_receipt_validation": "http://172.20.224.1/partners/",
    "ingame_dynamic_store": "http://172.20.224.1/store/",
    "ingame_dynamic_store_refresh_rat": "15",
    "microsoft_receipt_validation": "http://172.20.224.1/partners/windows/",
    "msdk_ingame_dynamic_store": "http://172.20.224.1/store/v2/",
    "tapjoy_reward_check": "http://172.20.224.1/partners/tapjoy/",
    "trialpay_reward_check": "http://172.20.224.1/partners/trialpay/",
    "user_profile": "http://172.20.224.1/profile/",
    "use_magnet_1_0": "yes",
    "use_magnet_2_0": "no",
    "use_cp2": "1",
    "environment": "production"
}).encode("utf-8")

REGISTER_DEVICE = json.dumps({
    "device": {
        "federated_id": "kL0R7Od1toC3MljqCGepVM1ET77yOd6dY656Vi7pHKym5SNIy17uO98Hhfg5sWir",
        "ubimobi_access_token": "YZLnU3wSjysqDwCL5o96BLJu1bvqh9Zg9LD3RaWbJFBmDe70Dh7e3RJ52fvkouBy"
    }
}).encode("utf-8")

UBI_SESSION = json.dumps({
    "environment": "Prod",
    "ticket": "v1.mock_ticket_1234567890",
    "twoFactorAuthenticationTicket": None,
    "profileId": "00000000-0000-0000-0000-000000000001",
    "userId": "00000000-0000-0000-0000-000000000001",
    "nameOnPlatform": "RaymanPlayer",
    "sessionKey": "mock_session_key_123",
    "spaceId": "e0b7ffaa-09a0-423e-b0a7-822f485b24ed",
    "clientIp": "10.0.2.2",
    "serverTime": "2026-11-15T19:00:00.0000000Z",
    "sessionId": "mock_session_id_456"
}).encode("utf-8")

EMPTY_ENTITIES = json.dumps({"entities": []}).encode("utf-8")
GENERIC_OK = json.dumps({"status": 200, "result": "ok"}).encode("utf-8")

class MockHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.headers.get('Host', 'no-host')}] {self.command} {self.path} -> {args[0]}\n")
        sys.stderr.flush()

    def do_respond(self, data, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path
        if "/store/v2" in p or "msdk_ingame_dynamic_store" in p:
            self.do_respond(FIXED_STORE_DATA)
        elif "/store" in p:
            self.do_respond(FIXED_STORE_DATA)
        elif "product=708" in p or p.startswith("/?"):
            self.do_respond(HOUSTON_CONFIG)
        elif "entities" in p:
            self.do_respond(EMPTY_ENTITIES)
        else:
            self.do_respond(GENERIC_OK)

    def do_POST(self):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""
        p = self.path
        if "deviceconfig" in p:
            self.do_respond(DEVICE_CONFIG)
        elif "register_device" in p or "profile" in p:
            self.do_respond(REGISTER_DEVICE)
        elif "sessions" in p:
            self.do_respond(UBI_SESSION)
        elif "entities" in p:
            self.do_respond(EMPTY_ENTITIES)
        else:
            self.do_respond(GENERIC_OK)

    def do_PUT(self):
        self.do_respond(GENERIC_OK)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_http():
    server = http.server.ThreadingHTTPServer(('0.0.0.0', 80), MockHandler)
    print("HTTP mock server listening on port 80...")
    sys.stdout.flush()
    server.serve_forever()

def run_https():
    cert_file = os.path.join(SCRATCH_DIR, "cert.pem")
    key_file = os.path.join(SCRATCH_DIR, "key.pem")
    server = http.server.ThreadingHTTPServer(('0.0.0.0', 443), MockHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("HTTPS mock server listening on port 443...")
    sys.stdout.flush()
    server.serve_forever()

if __name__ == '__main__':
    t_http = threading.Thread(target=run_http, daemon=True)
    t_https = threading.Thread(target=run_https, daemon=True)
    t_http.start()
    t_https.start()
    t_http.join()
    t_https.join()
