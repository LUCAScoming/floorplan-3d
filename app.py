# 户型装修方案 · Python 本地服务器（跨平台）
#
# 功能：
#   - 托管现有网页界面（index.html + libs/），浏览器直接访问，任何平台可用
#   - 方案存取 API：方案 JSON 保存在 plans/ 目录，可保存 / 打开 / 删除
#
# 启动：  python app.py            （监听 0.0.0.0:8765，自动打开浏览器）
# 依赖：  pip install -r requirements.txt
"""Floor-plan design app: local FastAPI server hosting the web UI and plan storage API."""
import json
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
PLANS_DIR = ROOT / "plans"
PORT = 8765

app = FastAPI(title="户型装修方案服务器", docs_url=None, redoc_url=None)


def plan_path(name: str) -> Path:
    """校验方案名（防路径穿越），返回对应的 JSON 文件路径。"""
    name = name.strip()
    if not name or len(name) > 80 or "/" in name or "\\" in name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="方案名不合法")
    return PLANS_DIR / (name + ".json")


@app.get("/api/plans")
def list_plans():
    """列出服务器上保存的所有方案（按修改时间倒序）。"""
    if not PLANS_DIR.exists():
        return []
    items = []
    for f in PLANS_DIR.glob("*.json"):
        try:
            st = f.stat()
        except OSError:
            continue
        items.append({"name": f.stem, "size": st.st_size, "mtime": st.st_mtime})
    items.sort(key=lambda x: -x["mtime"])
    return items


@app.get("/api/plans/{name}")
def get_plan(name: str):
    p = plan_path(name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="方案不存在")
    return FileResponse(p, media_type="application/json")


@app.put("/api/plans/{name}")
async def save_plan(name: str, request: Request):
    """保存方案：先写临时文件再原子替换，避免写一半损坏。"""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON")
    if not isinstance(data, dict) or not isinstance(data.get("furniture"), list):
        raise HTTPException(status_code=400, detail="方案数据不完整")
    PLANS_DIR.mkdir(exist_ok=True)
    p = plan_path(name)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return {"ok": True}


@app.delete("/api/plans/{name}")
def delete_plan(name: str):
    p = plan_path(name)
    if p.exists():
        p.unlink()
    return {"ok": True}


app.mount("/libs", StaticFiles(directory=ROOT / "libs"), name="libs")


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


def _open_browser():
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{PORT}/")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
