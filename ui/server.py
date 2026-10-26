"""Loopback dashboard serving with an explicit public asset allowlist."""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


def create_dashboard_handler(project_root, api_key, api_port):
    PROJECT_ROOT = str(project_root)
    html_path = os.path.join(PROJECT_ROOT, "ui", "owner.html")
    injected_key = api_key
    class DashboardHandler(BaseHTTPRequestHandler):
        """Serve only the dashboard and its local assets, never project data."""
        def log_message(self, *args):
            pass

        def do_GET(self):
            # The page contains the local API key. Reject foreign Host names so
            # a website cannot read it after rebinding its DNS to loopback.
            try:
                host = urlsplit("//" + self.headers.get("Host", "")).hostname
            except ValueError:
                host = None
            if host not in {"localhost", "127.0.0.1", "::1"}:
                self.send_error(403, "Local dashboard host required")
                return
            route = urlsplit(self.path).path
            if route in ("/", "/ui/owner.html"):
                target = html_path
                content_type = "text/html; charset=utf-8"
            elif route.startswith("/ui/assets/"):
                asset_root = os.path.realpath(os.path.join(PROJECT_ROOT, "ui", "assets"))
                target = os.path.realpath(os.path.join(PROJECT_ROOT, route.lstrip("/")))
                if not target.startswith(asset_root + os.sep):
                    self.send_error(404)
                    return
                content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
            else:
                self.send_error(404)
                return
            try:
                with open(target, "rb") as asset:
                    body = asset.read()
            except OSError:
                self.send_error(404)
                return
            if target == html_path:
                runtime = json.dumps({"apiKey": injected_key, "apiBase": f"http://127.0.0.1:{api_port}"})
                runtime = runtime.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
                body = body.replace(b"__SALEYAR_RUNTIME_CONFIG__", runtime.encode("utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler
