#!/usr/bin/env python3
"""
Docker Codex Proxy — Multi-provider routeur.

Lit providers.yaml, lance un codex-relay par provider chat,
sert les endpoints /{name}/v1/models, /{name}/config, /{name}/v1/responses.
"""
import base64, json, os, re, subprocess, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import yaml

CONFIG_PATH = "/app/providers.yaml"
BASE_PORT = 4445

relays = {}  # {name: {port, proc, ...}}
directs = {}  # {name: {upstream, api_key}}

def load_config(path):
    with open(path) as f:
        raw = f.read()
    # Env var substitution
    def sub_env(m):
        val = os.environ.get(m.group(1) or m.group(2), "")
        return val
    raw = re.sub(r'\$\{([^}]+)\}|(\$[A-Za-z_][A-Za-z0-9_]*)', sub_env, raw)
    config = yaml.safe_load(raw)
    # Decode base64 keys
    for p in config.get("providers", []):
        ak = p.get("api_key", "")
        if ak.startswith("b64:"):
            p["api_key"] = base64.b64decode(ak[4:]).decode()
    return config

def start_providers(config):
    i = 0
    for p in config.get("providers", []):
        name = p["name"]
        upstream = p["upstream"]
        api_key = p.get("api_key", "")
        fmt = p.get("format", "responses")
        
        if fmt == "chat":
            port = BASE_PORT + i
            cmd = ["codex-relay", "--port", str(port), "--upstream", upstream]
            if api_key:
                cmd.extend(["--api-key", api_key])
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            relays[name] = {"port": port, "proc": proc}
            print(f"[INIT] {name} → relay :{port} → {upstream} (chat → responses)")
            i += 1
        else:
            directs[name] = {"upstream": upstream, "api_key": api_key}
            print(f"[INIT] {name} → direct → {upstream} (responses)")

class ProxyHandler(BaseHTTPRequestHandler):
    
    def _route(self):
        parts = self.path.strip("/").split("/")
        if len(parts) < 2:
            return None, self.path
        return parts[0], "/" + "/".join(parts[1:])
    
    def _auth_headers(self):
        return {
            "Content-Type": "application/json",
            "User-Agent": "CodexProxy/1.0",
        }
    
    def _proxy_relay(self, name, path, body=None, method="GET"):
        port = relays[name]["port"]
        target = f"http://127.0.0.1:{port}{path}"
        headers = self._auth_headers()
        if body:
            req = Request(target, data=body.encode(), headers=headers, method=method)
        else:
            req = Request(target, headers=headers)
        return urlopen(req, timeout=60)
    
    def _proxy_direct(self, name, path, body=None, method="GET"):
        p = directs[name]
        # Remove /v1 prefix from path since upstream already has it
        clean_path = re.sub(r'^/v1', '', path) if path else path
        target = p["upstream"].rstrip("/") + clean_path
        headers = self._auth_headers()
        headers["Authorization"] = f"Bearer {p['api_key']}"
        if body:
            req = Request(target, data=body.encode(), headers=headers, method=method)
        else:
            req = Request(target, headers=headers)
        return urlopen(req, timeout=60)
    
    def _forward(self, name, path, body=None, method="GET"):
        try:
            if name in relays:
                resp = self._proxy_relay(name, path, body, method)
            elif name in directs:
                resp = self._proxy_direct(name, path, body, method)
            else:
                self.send_error(404, f"Provider '{name}' not found")
                return
            
            data = resp.read()
            self.send_response(resp.status)
            ct = resp.headers.get("Content-Type", "application/json")
            if ct:
                self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(data)
            
        except HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")
    
    def _config_toml(self, name):
        clean = name.replace("-", "_")
        return f"""[model_providers.{clean}]
name = "{name}"
base_url = "http://127.0.0.1:4444/{name}/v1"
wire_api = "responses"
"""
    
    def do_GET(self):
        name, path = self._route()
        if name is None:
            self.send_error(400, "Missing provider (e.g. /opencode/v1/models)")
            return
        if path == "/config":
            toml = self._config_toml(name)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(toml.encode())
        else:
            self._forward(name, path, method="GET")
    
    def do_POST(self):
        name, path = self._route()
        if name is None:
            self.send_error(400, "Missing provider")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length else None
        self._forward(name, path, body, method="POST")
    
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.address_string()}] {args[0]} {args[1]}\n")

def main():
    print("[INIT] Loading providers.yaml...")
    config = load_config(CONFIG_PATH)
    print(f"[INIT] {len(config.get('providers', []))} provider(s)")
    
    print("[INIT] Starting providers...")
    start_providers(config)
    
    print("[INIT] Proxy on :4444")
    server = HTTPServer(("0.0.0.0", 4444), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INIT] Shutdown...")
        for r in relays.values():
            r["proc"].terminate()
        server.server_close()

if __name__ == "__main__":
    main()
