#!/usr/bin/env python3
"""
Lark MCP Proxy Skill

本地MCP代理，负责：
1. UAT管理（存储、刷新）
2. MCP请求转发（自动附加UAT）
3. OAuth授权（本地完成）

用法：
    python scripts/lark_mcp.py

环境变量：
    LARK_MCP_SERVER_URL - MCP服务器地址（默认: http://10.18.8.141:3000）
    LARK_APP_ID - 飞书应用ID
    LARK_APP_SECRET - 飞书应用密钥
    LARK_OAUTH_PORT - OAuth回调本地端口（默认: 38473）
"""

import os
import sys
import json
import time
import uuid
import socket
import webbrowser
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import requests

DEFAULT_SERVER_URL = "http://10.18.8.141:3000"
DEFAULT_OAUTH_PORT = 38475
DEFAULT_OAUTH_REDIRECT_URI = "http://localhost:38475/auth/lark"
DEFAULT_APP_ID = "cli_a93016dd2c381bc2"
DEFAULT_APP_SECRET = "FZFs05AXpQDhVtRJqF2pDfkVLmjHgdQ7"
UAT_TOKEN_FILE = Path(__file__).parent.parent / "config" / "uat_token.json"

TOOL_REQUIRED_SCOPES = {
    'feishu_search': ['search:docs:read'],
    'feishu_fetch_doc': ['docx:document:readonly'],
    'feishu_create_doc': ['docx:document', 'docx:document:create', 'wiki:node:read', 'wiki:node:create'],
    'feishu_update_doc': ['docx:document:write_only'],
    'feishu_get_user': ['contact:user.base:readonly'],
    'feishu_search_user': ['contact:user:search'],
}

def extract_missing_scopes(error_message: str) -> list:
    import re
    match = re.search(r'privileges under the user identity:\s*\[([^\]]+)\]', error_message)
    if match:
        return [s.strip() for s in match.group(1).split(',')]
    match = re.search(r'\[([^\]]+)\]', error_message)
    if match:
        scopes_str = match.group(1)
        if ':' in scopes_str and not scopes_str.startswith('API:'):
            return [s.strip() for s in scopes_str.split(',')]
    return []

def get_required_scopes_for_tool(tool_name: str) -> list:
    return TOOL_REQUIRED_SCOPES.get(tool_name, [])

def merge_scopes(existing: list, new: list) -> list:
    result = list(existing)
    for scope in new:
        if scope not in result:
            result.append(scope)
    return result


class UATManager:
    def __init__(self):
        self.uat = None
        self.refresh_token = None
        self.expires_at = 0
        self.refresh_expires_at = 0
        self.scopes = []

    def load(self):
        if UAT_TOKEN_FILE.exists():
            try:
                with open(UAT_TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    self.uat = data.get('uat')
                    self.refresh_token = data.get('refresh_token')
                    self.expires_at = data.get('expires_at', 0)
                    self.refresh_expires_at = data.get('refresh_expires_at', 0)
                    self.scopes = data.get('scopes', [])
                print(f"[UAT] Loaded from {UAT_TOKEN_FILE}")
                return True
            except Exception as e:
                print(f"[UAT] Load error: {e}")
        return False

    def save(self):
        UAT_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(UAT_TOKEN_FILE, 'w') as f:
            json.dump({
                'uat': self.uat,
                'refresh_token': self.refresh_token,
                'expires_at': self.expires_at,
                'refresh_expires_at': self.refresh_expires_at,
                'scopes': self.scopes
            }, f, indent=2)
        print(f"[UAT] Saved to {UAT_TOKEN_FILE}")

    def is_valid(self):
        if not self.uat:
            return False
        return time.time() < (self.expires_at - 300)

    def is_refresh_expired(self):
        if not self.refresh_token:
            return True
        return time.time() >= (self.refresh_expires_at - 3600)

    def set(self, uat: str, expires_in: int = 7200, refresh_token: str = None, refresh_expires_in: int = 0):
        self.uat = uat
        self.expires_at = time.time() + expires_in
        if refresh_token:
            self.refresh_token = refresh_token
            self.refresh_expires_at = time.time() + refresh_expires_in if refresh_expires_in else time.time() + 2591940
        self.save()

    def get(self) -> str:
        return self.uat

    def get_refresh_token(self) -> str:
        return self.refresh_token

    def clear(self):
        self.uat = None
        self.refresh_token = None
        self.expires_at = 0
        self.refresh_expires_at = 0
        if UAT_TOKEN_FILE.exists():
            UAT_TOKEN_FILE.unlink()
        print("[UAT] Cleared")


class LarkOAuth:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

    def get_authorization_url(self, redirect_uri: str, state: str, scopes: str = None) -> str:
        if scopes is None:
            scopes = 'docx:document:readonly'
        return (f"https://accounts.feishu.cn/open-apis/authen/v1/authorize"
                f"?app_id={self.app_id}"
                f"&redirect_uri={requests.utils.quote(redirect_uri)}"
                f"&scope={requests.utils.quote(scopes)}"
                f"&state={requests.utils.quote(state)}")

    def exchange_code_for_uat(self, code: str, redirect_uri: str) -> dict:
        print(f"   [DEBUG] Exchanging code with redirect_uri: {redirect_uri}")
        resp = requests.post(
            'https://accounts.feishu.cn/open-apis/authen/v2/oauth/token',
            data={
                'grant_type': 'authorization_code',
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'code': code,
                'redirect_uri': redirect_uri
            },
            timeout=30
        )
        print(f"   [DEBUG] Response status: {resp.status_code}")
        print(f"   [DEBUG] Response body: {resp.text[:500]}")
        resp.raise_for_status()
        result = resp.json()

        if result.get('code') != 0:
            raise Exception(result.get('msg', 'Failed to exchange code for UAT'))

        data = result
        return {
            'uat': data.get('access_token'),
            'expires_in': data.get('expires_in', 7200),
            'refresh_token': data.get('refresh_token'),
            'refresh_expires_in': data.get('refresh_expires_in', 2591940)
        }

    def refresh_uat(self, refresh_token: str) -> dict:
        resp = requests.post(
            'https://accounts.feishu.cn/open-apis/authen/v2/oauth/token',
            json={
                'grant_type': 'refresh_token',
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'refresh_token': refresh_token
            },
            timeout=30
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get('code') != 0:
            raise Exception(result.get('msg', 'Failed to refresh UAT'))

        data = result.get('data', {})
        return {
            'uat': data.get('access_token'),
            'expires_in': data.get('expires_in', 7200),
            'refresh_token': data.get('refresh_token'),
            'refresh_expires_in': data.get('refresh_expires_in', 2591940)
        }


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    oauth_result = None
    server_instance = None

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/auth/lark':
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]
            error = params.get('error', [None])[0]

            if error:
                OAuthCallbackHandler.oauth_result = {'error': error}
                self.send_response(400)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><body><h1>Authorization Failed</h1><p>You can close this window.</p></body></html>')
            elif code:
                OAuthCallbackHandler.oauth_result = {'code': code, 'state': state}
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><body><h1>Authorization Successful!</h1><p>You can close this window.</p></body></html>')
            else:
                self.send_response(400)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><body><h1>Invalid Callback</h1></body></html>')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        self.send_response(405)
        self.end_headers()


def find_available_port(start_port: int = DEFAULT_OAUTH_PORT) -> int:
    for port in range(start_port, start_port + 100):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('localhost', port))
            s.close()
            return port
        except OSError:
            continue
    raise Exception("Could not find available port")


def start_local_oauth_server(port: int):
    server = HTTPServer(('localhost', port), OAuthCallbackHandler)
    OAuthCallbackHandler.server_instance = server
    server.handle_request()
    return server


def authorize(uat_manager: UATManager, app_id: str, app_secret: str, additional_scopes: list = None):
    print("\n" + "=" * 50)
    print("Lark MCP Authorization")
    print("=" * 50)

    oauth = LarkOAuth(app_id, app_secret)
    state = str(uuid.uuid4())

    port = DEFAULT_OAUTH_PORT
    redirect_uri = DEFAULT_OAUTH_REDIRECT_URI

    print(f"\n1. OAuth callback will use: {redirect_uri}")

    scopes = list(uat_manager.scopes) if uat_manager.scopes else ['docx:document:readonly']
    if additional_scopes:
        scopes = merge_scopes(scopes, additional_scopes)
    scopes_str = ' '.join(scopes)
    print(f"\n2. Requesting scopes: {scopes_str}")

    print(f"\n3. Getting authorization URL...")
    try:
        auth_url = oauth.get_authorization_url(redirect_uri, state, scopes_str)
        print(f"   URL: {auth_url[:80]}...")
    except Exception as e:
        print(f"   Error: {e}")
        return False

    print(f"\n4. Opening browser for authorization...")
    print(f"   (If browser doesn't open, visit the URL above)")
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        print(f"   [WARN] Browser open failed: {e}")
        print(f"   Please manually visit: {auth_url}")

    print(f"\n5. Waiting for callback on port {port}...")
    server_started = time.time()
    server_timeout = 300

    try:
        server = HTTPServer(('localhost', port), OAuthCallbackHandler)
        OAuthCallbackHandler.oauth_result = None

        while time.time() - server_started < server_timeout:
            server.handle_request()
            result = OAuthCallbackHandler.oauth_result

            if result:
                server.server_close()
                break

        if not result:
            print(f"\n[FAILED] Authorization timeout")
            server.server_close()
            return False

        if 'error' in result:
            print(f"\n[FAILED] Authorization error: {result['error']}")
            return False

        code = result.get('code')
        print(f"\n6. Received code, exchanging for UAT...")

        token_result = oauth.exchange_code_for_uat(code, redirect_uri)
        uat_manager.scopes = scopes
        uat_manager.set(
            token_result['uat'],
            token_result['expires_in'],
            token_result.get('refresh_token'),
            token_result.get('refresh_expires_in', 0)
        )

        print(f"\n[OK] Authorization successful!")
        print(f"     UAT saved to {UAT_TOKEN_FILE}")
        print(f"     Refresh token: {'present' if token_result.get('refresh_token') else 'not available'}")
        return True

    except Exception as e:
        print(f"\n[FAILED] Authorization failed: {e}")
        return False


class MCPProxy:
    def __init__(self, server_url: str, uat_manager: UATManager, app_id: str = None, app_secret: str = None):
        self.server_url = server_url.rstrip('/')
        self.uat_manager = uat_manager
        self.app_id = app_id or os.environ.get('LARK_APP_ID', DEFAULT_APP_ID)
        self.app_secret = app_secret or os.environ.get('LARK_APP_SECRET', DEFAULT_APP_SECRET)
        self.lark_oauth = LarkOAuth(self.app_id, self.app_secret) if self.app_id and self.app_secret else None

    def refresh_if_needed(self) -> bool:
        if not self.lark_oauth:
            return False

        if not self.uat_manager.is_valid() and self.uat_manager.get_refresh_token():
            if not self.uat_manager.is_refresh_expired():
                print("[MCP] UAT expired, attempting refresh...")
                try:
                    result = self.lark_oauth.refresh_uat(self.uat_manager.get_refresh_token())
                    self.uat_manager.set(
                        result['uat'],
                        result['expires_in'],
                        result.get('refresh_token'),
                        result.get('refresh_expires_in', 0)
                    )
                    print("[MCP] UAT refreshed successfully")
                    return True
                except Exception as e:
                    print(f"[MCP] UAT refresh failed: {e}")
        return False

    def handle_request(self, method: str, params: dict = None) -> dict:
        self.refresh_if_needed()

        request_id = str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        uat = self.uat_manager.get()
        if uat:
            headers["X-Lark-MCP-UAT"] = uat

        print(f"[MCP] -> {method}")
        print(f"[MCP] Payload: {json.dumps(payload, indent=2)[:500]}")
        print(f"[MCP] UAT present: {bool(uat)}")

        try:
            resp = requests.post(
                self.server_url,
                headers=headers,
                json=payload,
                timeout=60
            )

            print(f"[MCP] Response status: {resp.status_code}")
            print(f"[MCP] Response body: {resp.text[:1000]}")

            if resp.status_code == 200:
                result = resp.json()
                print(f"[MCP] <- {method} (success)")
                return result
            else:
                print(f"[MCP] <- {method} (error: {resp.status_code})")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": resp.status_code, "message": resp.text[:500]}
                }

        except Exception as e:
            print(f"[MCP] Exception: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)}
            }


def main():
    server_url = os.environ.get("LARK_MCP_SERVER_URL", DEFAULT_SERVER_URL)
    app_id = os.environ.get('LARK_APP_ID', DEFAULT_APP_ID)
    app_secret = os.environ.get('LARK_APP_SECRET', DEFAULT_APP_SECRET)
    #sys.argv = ["","auth"]
    uat_manager = UATManager()
    uat_manager.load()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "auth":
            if not app_id or not app_secret:
                print("[ERROR] LARK_APP_ID and LARK_APP_SECRET environment variables are required")
                print("        Set them via environment variables or command line")
                sys.exit(1)

            additional_scopes = None
            if len(sys.argv) > 3 and sys.argv[2] == "--add-scope":
                additional_scopes = sys.argv[3].split(',') if len(sys.argv) > 3 else []
                print(f"[AUTH] Additional scopes requested: {additional_scopes}")

            if additional_scopes:
                uat_manager.scopes = merge_scopes(uat_manager.scopes, additional_scopes)

            authorize(uat_manager, app_id, app_secret, additional_scopes)

        elif command == "check":
            if uat_manager.is_valid():
                remaining = int(uat_manager.expires_at - time.time())
                print(f"[OK] UAT is valid")
                print(f"     Expires in: {remaining} seconds")
                if uat_manager.get_refresh_token():
                    refresh_remaining = int(uat_manager.refresh_expires_at - time.time())
                    print(f"     Refresh token expires in: {refresh_remaining} seconds")
            else:
                print("[WARN] UAT is invalid or expired")
                print("       Run 'python scripts/lark_mcp.py auth' to authorize")

        elif command == "clear":
            uat_manager.clear()

        elif command == "tools":
            proxy = MCPProxy(server_url, uat_manager, app_id, app_secret)
            result = proxy.handle_request("tools/list")

            if "result" in result:
                tools = result["result"].get("tools", [])
                print(f"\nAvailable tools ({len(tools)}):")
                for tool in tools:
                    print(f"  - {tool['name']}")
            else:
                print(f"[ERROR] {result}")

        elif command == "invoke":
            if len(sys.argv) < 3:
                print("Usage: invoke <tool_name> [args_json]")
                sys.exit(1)

            tool_name = sys.argv[2]
            args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

            proxy = MCPProxy(server_url, uat_manager, app_id, app_secret)
            result = proxy.handle_request("tools/call", {
                "name": tool_name,
                "arguments": args
            })

            if "result" in result and result["result"].get("isError"):
                content = result["result"].get("content", [])
                for item in content:
                    if item.get("type") == "text":
                        error_text = item.get("text", "")
                        missing_scopes = extract_missing_scopes(error_text)
                        if missing_scopes:
                            new_scopes = [s for s in missing_scopes if s not in uat_manager.scopes]
                            if new_scopes:
                                print(f"[PERMISSION] Missing scopes detected: {new_scopes}")
                                print(f"[PERMISSION] Re-authorizing to add missing scopes...")
                                uat_manager.scopes = merge_scopes(uat_manager.scopes, new_scopes)
                                if authorize(uat_manager, app_id, app_secret, new_scopes):
                                    print(f"[PERMISSION] Re-authorization successful, retrying invoke...")
                                    uat_manager.load()
                                    result = proxy.handle_request("tools/call", {
                                        "name": tool_name,
                                        "arguments": args
                                    })
                                else:
                                    print(f"[PERMISSION] Re-authorization failed")
                            else:
                                print(f"[PERMISSION] All missing scopes already authorized")

            print(json.dumps(result, indent=2, ensure_ascii=False))

        else:
            print(f"Unknown command: {command}")
            print("Available: auth, check, clear, tools, invoke")

    else:
        if not uat_manager.is_valid():
            print("[WARN] UAT is invalid or expired")
            print("       Run 'python scripts/lark_mcp.py auth' to authorize")

        print(f"\n[MCP Proxy] Server: {server_url}")
        print(f"[MCP Proxy] UAT: {'valid' if uat_manager.is_valid() else 'invalid/expired'}")

        if uat_manager.is_valid():
            print("\nTrying to list tools...")
            proxy = MCPProxy(server_url, uat_manager, app_id, app_secret)
            result = proxy.handle_request("tools/list")

            if "result" in result:
                tools = result["result"].get("tools", [])
                print(f"Found {len(tools)} tools")
            elif "error" in result:
                print(f"Error: {result['error']}")
        else:
            print("\nCommands:")
            print("  python scripts/lark_mcp.py auth      # Authorize")
            print("  python scripts/lark_mcp.py check     # Check UAT")
            print("  python scripts/lark_mcp.py tools     # List tools")


if __name__ == "__main__":
    main()