# 户型装修方案 · 本地服务器（纯 Python 标准库，无第三方依赖）
# 功能：托管网页界面（index.html + libs/）；方案存取 API（JSON，原子写入防损坏）
# 启动：python app.py [--port 8765] [--data-dir plans]
#       飞牛 fnOS 原生应用由 cmd/main 传入 --port 与 --data-dir（应用数据目录）
"""Floor-plan app: stdlib-only server hosting the web UI and plan storage API."""
import argparse, json, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE = Path(__file__).resolve().parent
# 网页目录：脚本同级有 index.html 就用同级（本地直接运行），否则用 www/ 子目录（fnOS 应用包）
WWW = BASE if (BASE / "index.html").exists() else BASE / "www"
LIBS = WWW / "libs"
DATA_DIR = BASE / "plans"          # 可被 --data-dir 覆盖

CTYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".json": "application/json; charset=utf-8", ".png": "image/png",
          ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon",
          ".wasm": "application/wasm", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}


def plan_path(name: str) -> Path:
    """校验方案名（防路径穿越），返回对应的 JSON 文件路径。"""
    name = name.strip()
    if not name or len(name) > 80 or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("方案名不合法")
    return DATA_DIR / (name + ".json")


class Handler(BaseHTTPRequestHandler):
    server_version = "FloorPlanServer/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _reply(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path):
        try:
            body = path.read_bytes()
        except OSError:
            self._reply(404, {"detail": "文件不存在"})
            return
        self._reply(200, body, CTYPES.get(path.suffix.lower(), "application/octet-stream"))

    def _static(self, url_path: str):
        if url_path == "/":
            self._serve_file(WWW / "index.html")
            return True
        if url_path.startswith("/libs/"):
            f = (LIBS / unquote(url_path[len("/libs/"):])).resolve()
            if LIBS.resolve() not in f.parents and f != LIBS.resolve():
                self._reply(403, {"detail": "路径不合法"})
            elif f.is_file():
                self._serve_file(f)
            else:
                self._reply(404, {"detail": "文件不存在"})
            return True
        return False

    def _plan_name(self):
        return plan_path(unquote(urlsplit(self.path).path[len("/api/plans/")]))

    def do_GET(self):
        path = urlsplit(self.path).path
        if self._static(path):
            return
        if path == "/api/plans":
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            items = []
            for f in DATA_DIR.glob("*.json"):
                try:
                    st = f.stat()
                except OSError:
                    continue
                items.append({"name": f.stem, "size": st.st_size, "mtime": st.st_mtime})
            items.sort(key=lambda x: -x["mtime"])
            self._reply(200, items)
        elif path.startswith("/api/plans/"):
            try:
                p = self._plan_name()
            except ValueError as e:
                self._reply(400, {"detail": str(e)}); return
            if not p.exists():
                self._reply(404, {"detail": "方案不存在"})
            else:
                self._serve_file(p)
        else:
            self._reply(404, {"detail": "接口不存在"})

    def do_PUT(self):
        if not urlsplit(self.path).path.startswith("/api/plans/"):
            self._reply(404, {"detail": "接口不存在"}); return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 64 * 1024 * 1024:
            self._reply(400, {"detail": "请求体大小异常"}); return
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            self._reply(400, {"detail": "请求体不是合法 JSON"}); return
        if not isinstance(data, dict) or not isinstance(data.get("furniture"), list):
            self._reply(400, {"detail": "方案数据不完整"}); return
        try:
            p = self._plan_name()
        except ValueError as e:
            self._reply(400, {"detail": str(e)}); return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")    # 先写临时文件再原子替换，避免写一半损坏
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
        self._reply(200, {"ok": True})

    def do_DELETE(self):
        if not urlsplit(self.path).path.startswith("/api/plans/"):
            self._reply(404, {"detail": "接口不存在"}); return
        try:
            p = self._plan_name()
        except ValueError as e:
            self._reply(400, {"detail": str(e)}); return
        if p.exists():
            p.unlink()
        self._reply(200, {"ok": True})


def main():
    ap = argparse.ArgumentParser(description="户型装修方案服务器")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", default=str(BASE / "plans"))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    global DATA_DIR
    DATA_DIR = Path(args.data_dir)
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(
            "http://localhost:%d/" % args.port)), daemon=True).start()
    print("户型装修方案服务器: http://0.0.0.0:%d  (网页目录 %s, 方案目录 %s)"
          % (args.port, WWW, DATA_DIR), flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
