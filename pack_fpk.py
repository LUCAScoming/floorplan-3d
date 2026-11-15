"""户型装修设计 · 飞牛 fnOS 应用中心打包脚本（.fpk）

.fpk 是飞牛 NAS（fnOS）应用中心的应用安装包，本质是 tar.gz，内部结构：
manifest（元数据，含 app.tgz 的 MD5）、app.tgz（www 站点 + docker compose + app.py）、
cmd/main（生命周期）、config/（权限与资源）、ui/（桌面入口与图标）、
<appname>.sc（端口声明）、health.json（健康检查）、ICON 图标。

应用以 Docker 方式运行：python:3.12-slim 容器内启动 FastAPI（app.py），
托管纯前端界面与 /api/plans 方案 API，容器内端口 8765。

用法：python pack_fpk.py [版本号]    （默认 1.0.0，产物：floorplan3d-<版本>.fpk）
安装：fnOS 应用中心右上角「手动安装」→ 选择 .fpk 文件。
注意：按社区验证过的 fpk 结构编写，首次安装请先在 fnOS 上手动验证。
"""
import hashlib
import json
import shutil
import struct
import sys
import tarfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPNAME = "floorplan3d"
DISPLAY_NAME = "户型装修设计"
PORT = 8765

WWW_FILES = ["index.html", "libs", "LICENSE", "README.md"]          # 打进 www 的纯前端文件
EXCLUDE = {".env", ".git", "__pycache__", ".playwright-cli", "plans",
           "server.log", ".codebuddy", "node_modules", ".idea", ".vscode"}


# ---------------------------------------------------------------- PNG 图标生成（纯 Python，无需 PIL）
def make_icon_png(size: int) -> bytes:
    """深蓝底 + 白色小房子（三角屋顶 + 方形屋身 + 门）。"""
    bg, fg = (40, 90, 180), (245, 248, 255)
    px = [[bg] * size for _ in range(size)]

    def fill(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                px[y][x] = c

    u = size / 64.0                       # 以 64 为基准的缩放单位
    fill(int(14 * u), int(26 * u), int(50 * u), int(50 * u), fg)          # 屋身
    cx = size / 2
    top = int(8 * u)                                                      # 屋顶三角
    for y in range(top, int(28 * u)):
        w = int(26 * u * (y - top) / max(1, int(20 * u))) + 1
        fill(int(cx - w), y, int(cx + w), y + 1, fg)
    fill(int(27 * u), int(36 * u), int(37 * u), int(50 * u), bg)          # 门
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


# ---------------------------------------------------------------- 各 fpk 组件内容
def manifest_text(version: str, checksum: str) -> str:
    return (f"appname = {APPNAME}\nversion = {version}\ndisplay_name = {DISPLAY_NAME}\n"
            f"platform = all\nmaintainer = RONGLINC93\n"
            f"maintainer_url = https://github.com/RONGLINC93/floorplan-3d\n"
            f"distributor = RONGLINC93\n"
            f"distributor_url = https://github.com/RONGLINC93/floorplan-3d\n"
            f"desktop_uidir = ui\ndesktop_applaunchname = {APPNAME}.Application\n"
            f"service_port = {PORT}\n"
            f"desc = 纯前端的户型装修设计工具：2D 平面图摆放家具、拆改墙体、测量尺寸，"
            f"一键切换 Three.js 3D 场景鸟瞰或第一人称漫游，支持方案保存到服务器。仅供学习交流使用。\n"
            f"source = thirdparty\nchecksum = {checksum}\n")


def compose_yaml() -> str:
    return (f"services:\n  {APPNAME}:\n    image: python:3.12-slim\n"
            f"    container_name: {APPNAME}\n    working_dir: /app\n"
            f"    command: >\n      sh -c \"pip install --no-cache-dir -r requirements.txt &&\n"
            f"             python app.py\"\n    volumes:\n      - ../:/app:ro\n"
            f"    ports:\n      - \"{PORT}:{PORT}\"\n    restart: unless-stopped\n")


def cmd_main() -> str:
    return """#!/bin/bash

FILE_PATH="${TRIM_APPDEST}/docker/docker-compose.yaml"

is_docker_running () {
    DOCKER_NAME=""
    if [ -f "$FILE_PATH" ]; then
        DOCKER_NAME=$(cat $FILE_PATH | grep "container_name" | awk -F ':' '{print $2}' | xargs)
    fi
    if [ -n "$DOCKER_NAME" ]; then
        docker inspect $DOCKER_NAME | grep -q '"Status": "running",' || exit 1
        return
    fi
}

case $1 in
start) exit 0 ;;
stop) exit 0 ;;
status) if is_docker_running; then exit 0; else exit 3; fi ;;
*) exit 1 ;;
esac
"""


def config_resource() -> str:
    return json.dumps({
        "port-config": {"protocol-file": f"{APPNAME}.sc"},
        "data-share": {"shares": [{"name": DISPLAY_NAME,
                                   "permission": {"rw": [APPNAME]}}]},
        "docker-project": {"projects": [{"name": APPNAME, "path": "docker"}]},
    }, ensure_ascii=False, indent=4)


def ui_config(version: str) -> str:
    return json.dumps({".url": {f"{APPNAME}.Application": {
        "title": DISPLAY_NAME,
        "desc": f"{DISPLAY_NAME} - 2D 平面布置 + 3D 漫游（v{version}）",
        "icon": "images/{0}.png",
        "type": "url", "port": str(PORT), "protocol": "http",
        "url": "/", "allUsers": True,
    }}}, ensure_ascii=False, indent=4)


def health_json() -> str:
    return json.dumps({"type": "http", "path": "/",
                       "expect_status": [200, 301, 302, 401, 403],
                       "startup_timeout_seconds": 120,
                       "post_install_warmup_seconds": 0,
                       "skip_arch": [], "note": ""}, indent=4)


def sc_text() -> str:
    return (f"[{APPNAME}]\ntitle=\"{DISPLAY_NAME}\"\n"
            f"desc=\"Floor Plan Interior Designer\"\nport_forward=\"yes\"\n"
            f"src.ports=\"{PORT}/tcp\"\ndst.ports=\"{PORT}/tcp\"\n")


# ---------------------------------------------------------------- 打包
def build_app_tgz(stage: Path) -> str:
    """组装 app/（www + docker + app.py）并压成 app.tgz，返回其 MD5。"""
    app = stage / "app"
    www = app / "www"
    for item in WWW_FILES:
        src = ROOT / item
        dst = www / item
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
        elif src.is_dir():
            for f in src.rglob("*"):
                if f.is_file() and not any(p in EXCLUDE for p in f.relative_to(src).parts) \
                        and f.suffix.lower() != ".pyc":
                    rel_dst = dst / f.relative_to(src)
                    rel_dst.parent.mkdir(parents=True, exist_ok=True)
                    rel_dst.write_bytes(f.read_bytes())

    docker = app / "docker"
    docker.mkdir(parents=True, exist_ok=True)
    (docker / "docker-compose.yaml").write_text(compose_yaml(), encoding="utf-8", newline="\n")
    for f in ("app.py", "requirements.txt"):      # compose 把 .. 挂载为 /app 运行
        (app / f).write_bytes((ROOT / f).read_bytes())

    add_tree_tar(stage / "app.tgz", app, exec_names=set())
    return hashlib.md5((stage / "app.tgz").read_bytes()).hexdigest()


def add_tree_tar(out: Path, src_root: Path, exec_names: set):
    """把目录打成 tar.gz：目录 755、普通文件 644、exec_names 中的文件 755（fnOS 要求脚本可执行）。"""
    with tarfile.open(out, "w:gz") as z:
        ti = z.gettarinfo(src_root, arcname=".")
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = "root"
        ti.mode = 0o755
        z.addfile(ti)
        for f in sorted(src_root.rglob("*")):
            rel = f.relative_to(src_root).as_posix()
            ti = z.gettarinfo(f, arcname="./" + rel)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = "root"
            ti.mode = 0o755 if (f.is_dir() or rel in exec_names) else 0o644
            if f.is_file():
                with open(f, "rb") as fh:
                    z.addfile(ti, fh)
            else:
                z.addfile(ti)


def do_pack(version: str) -> None:
    out = ROOT / f"{APPNAME}-{version}.fpk"
    stage = ROOT / ".fpk_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()

    print("[1/4] 组装 app.tgz（www + docker + app.py）...")
    md5 = build_app_tgz(stage)
    shutil.rmtree(stage / "app")

    print("[2/4] 写入 manifest / cmd / config / ui / 健康检查 ...")
    (stage / "manifest").write_text(manifest_text(version, md5), encoding="utf-8", newline="\n")
    (stage / "cmd").mkdir()
    (stage / "cmd" / "main").write_text(cmd_main(), encoding="utf-8", newline="\n")
    (stage / "config").mkdir()
    (stage / "config" / "privilege").write_text("run-as=package\n", encoding="utf-8", newline="\n")
    (stage / "config" / "resource").write_text(config_resource(), encoding="utf-8", newline="\n")
    ui = stage / "ui"
    (ui / "images").mkdir(parents=True)
    (ui / "config").write_text(ui_config(version), encoding="utf-8", newline="\n")

    print("[3/4] 生成图标 ...")
    for s in (64, 128, 256):
        (ui / "images" / f"{s}.png").write_bytes(make_icon_png(s))
    (stage / "ICON.PNG").write_bytes(make_icon_png(64))
    (stage / "ICON_256.PNG").write_bytes(make_icon_png(256))

    (stage / f"{APPNAME}.sc").write_text(sc_text(), encoding="utf-8", newline="\n")
    (stage / "health.json").write_text(health_json(), encoding="utf-8", newline="\n")

    print("[4/4] 打包 .fpk（tar.gz，cmd/main 加可执行权限）...")
    add_tree_tar(out, stage, exec_names={"cmd/main"})
    shutil.rmtree(stage)
    print(f"[ok] 已生成 {out.name}（{out.stat().st_size / 1024 / 1024:.1f} MB，app.tgz MD5 {md5[:8]}...）")
    print("[i] 安装：fnOS 应用中心 → 手动安装 → 选择该 .fpk（需先开启 Docker）")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
    do_pack(version)


if __name__ == "__main__":
    main()
