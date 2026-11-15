"""户型装修设计 · 飞牛 fnOS 应用中心打包脚本（.fpk）

按 fnOS 开放平台规范生成完整应用工程并用官方 fnpack 工具打包：
    .fpk = tar.gz，顶层含 manifest / app.tgz / cmd/（9 个生命周期脚本）/
    config/privilege+resource / ICON.PNG / ICON_256.PNG / LICENSE / floorplan3d.sc
    app.tgz 内含 www/（前端）、docker/docker-compose.yaml、app.py、ui/config

用法：python pack_fpk.py [版本号]    （默认 1.0.0，产物：floorplan3d-<版本>.fpk）
安装：fnOS 应用中心 → 手动安装 → 选择 .fpk（需先开启 Docker）
"""
import hashlib
import json
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPNAME = "floorplan3d"
DISPLAY_NAME = "户型装修设计"
PORT = 8765
FNPACK_VERSION = "1.2.3"
FNPACK_URLS = {
    "windows": f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-windows-amd64",
    "linux": f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-linux-amd64",
    "darwin": f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-darwin-amd64",
}

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

    u = size / 64.0
    fill(int(14 * u), int(26 * u), int(50 * u), int(50 * u), fg)
    cx = size / 2
    top = int(8 * u)
    for y in range(top, int(28 * u)):
        w = int(26 * u * (y - top) / max(1, int(20 * u))) + 1
        fill(int(cx - w), y, int(cx + w), y + 1, fg)
    fill(int(27 * u), int(36 * u), int(37 * u), int(50 * u), bg)
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- fnpack 工程各文件内容
def manifest_text(version: str) -> str:
    """fnOS manifest：key=value 紧凑格式（等号两侧不能有空格）。"""
    return (f"appname={APPNAME}\n"
            f"version={version}\n"
            f"display_name={DISPLAY_NAME}\n"
            f"desc=纯前端的户型装修设计工具：2D 平面图摆放家具、拆改墙体、测量尺寸，"
            f"一键切换 Three.js 3D 场景鸟瞰或第一人称漫游，支持方案保存到服务器。仅供学习交流使用。\n"
            f"source=thirdparty\n"
            f"platform=all\n"
            f"maintainer=RONGLINC93\n"
            f"maintainer_url=https://github.com/RONGLINC93/floorplan-3d\n"
            f"distributor=RONGLINC93\n"
            f"distributor_url=https://github.com/RONGLINC93/floorplan-3d\n"
            f"os_min_version=1.0.0\n"
            f"desktop_uidir=ui\n"
            f"desktop_applaunchname={APPNAME}.main\n"
            f"service_port={PORT}\n"
            f"checkport=true\n"
            f"ctl_stop=true\n"
            f"disable_authorization_path=true\n"
            f"changelog={version} 首个版本：本地服务器托管 + 服务器端方案存储 + 依赖库本地化离线可用。\n")


def compose_yaml() -> str:
    return (f"services:\n  {APPNAME}:\n    image: ${{wizard_image:-python:3.12-slim}}\n"
            f"    container_name: {APPNAME}\n    working_dir: /app\n"
            f"    command: >\n      sh -c \"pip install --no-index --find-links=/app/deps\n"
            f"             -r requirements.txt && python app.py\"\n    volumes:\n"
            f"      - ../:/app:ro\n"
            f"    ports:\n      - \"{PORT}:{PORT}\"\n    restart: unless-stopped\n")


SHEBANG = "#!/bin/bash\n"


def cmd_scripts() -> dict:
    """fnOS 要求的 9 个生命周期脚本（LF、#!/bin/bash、需 755）。"""
    main = SHEBANG + f"""
FILE_PATH="${{TRIM_APPDEST}}/docker/docker-compose.yaml"

is_docker_running () {{
    DOCKER_NAME=""
    if [ -f "$FILE_PATH" ]; then
        DOCKER_NAME=$(cat $FILE_PATH | grep "container_name" | awk -F ':' '{{print $2}}' | xargs)
    fi
    if [ -n "$DOCKER_NAME" ]; then
        docker inspect $DOCKER_NAME | grep -q '"Status": "running",' || exit 1
        return
    fi
}}

case $1 in
start) exit 0 ;;
stop) exit 0 ;;
status) if is_docker_running; then exit 0; else exit 3; fi ;;
*) exit 1 ;;
esac
"""
    stub = SHEBANG + "# 由 fnOS 平台托管容器启停，此处无需额外操作\nexit 0\n"
    return {"main": main,
            "install_init": stub, "install_callback": stub,
            "upgrade_init": stub, "upgrade_callback": stub,
            "uninstall_init": stub, "uninstall_callback": stub,
            "config_init": stub, "config_callback": stub}


def config_resource() -> str:
    # 与已验证可安装的参考工程一致：最小化声明，只保留 docker-project
    return json.dumps({
        "docker-project": {"projects": [{"name": APPNAME, "path": "docker"}]},
    }, ensure_ascii=False, indent=4)


def ui_config(version: str) -> str:
    # key 必须与 manifest 的 desktop_applaunchname 一致
    return json.dumps({".url": {f"{APPNAME}.main": {
        "title": DISPLAY_NAME,
        "desc": f"{DISPLAY_NAME} - 2D 平面布置 + 3D 漫游（v{version}）",
        "icon": "images/{0}.png",
        "type": "url", "port": str(PORT), "protocol": "http",
        "url": "/", "allUsers": True,
    }}}, ensure_ascii=False, indent=4)


def wizard_json(title: str) -> str:
    """向导 JSON：步骤数组，items 里 type=tips/text；字段名即注入 compose 的环境变量名。"""
    return json.dumps([{
        "stepTitle": title,
        "items": [
            {"type": "tips",
             "helpText": "【镜像地址】保持默认即可。国内拉取 python 镜像慢或失败时，"
                         "可改成可用的加速地址；已用 docker load 导入本机时，改成导入后的 tag。"},
            {"type": "text", "field": "wizard_image", "label": "镜像地址",
             "initValue": "python:3.12-slim",
             "rules": [{"pattern": "^\\S+$", "message": "镜像地址不能包含空格；留空自动用默认地址"}]},
        ],
    }], ensure_ascii=False)


def sc_text() -> str:
    return (f"[{APPNAME}]\ntitle=\"{DISPLAY_NAME}\"\n"
            f"desc=\"Floor Plan Interior Designer\"\nport_forward=\"yes\"\n"
            f"src.ports=\"{PORT}/tcp\"\ndst.ports=\"{PORT}/tcp\"\n")


# ---------------------------------------------------------------- 离线依赖 wheel
def ensure_deps(dst: Path):
    """用本机 pip 下载 Linux x86_64 / CPython 3.12 的依赖 wheel，容器内离线安装。
    缓存在 tools/deps，避免重复下载。"""
    cache = ROOT / "tools" / "deps"
    if not cache.exists() or not any(cache.glob("*.whl")):
        print("[i] 下载 Linux 平台依赖 wheel（首次较慢）...")
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "download",
             "-r", str(ROOT / "requirements.txt"),
             "--only-binary=:all:",
             "--python-version", "312",
             "--platform", "manylinux2014_x86_64",
             "-d", str(cache)],
            check=True)
    dst.mkdir(parents=True, exist_ok=True)
    for whl in cache.glob("*.whl"):
        shutil.copy(whl, dst / whl.name)


# ---------------------------------------------------------------- 组装 fnpack 工程目录
def build_project(stage: Path, version: str) -> Path:
    """生成 fnpack 要求的应用工程目录结构。"""
    proj = stage / "fnos" / APPNAME
    app = proj / "app"

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

    (app / "docker").mkdir(parents=True, exist_ok=True)
    (app / "docker" / "docker-compose.yaml").write_text(compose_yaml(), encoding="utf-8", newline="\n")
    for f in ("app.py", "requirements.txt"):      # compose 把 app.tgz 解压根（..）挂载为 /app
        (app / f).write_bytes((ROOT / f).read_bytes())
    ensure_deps(app / "deps")                     # Linux 平台 wheel，容器内离线安装

    ui = app / "ui"
    ui.mkdir(parents=True, exist_ok=True)
    (ui / "images").mkdir(exist_ok=True)
    (ui / "config").write_text(ui_config(version), encoding="utf-8", newline="\n")
    for s in (64, 128, 256):
        (ui / "images" / f"{s}.png").write_bytes(make_icon_png(s))

    cmd = proj / "cmd"
    cmd.mkdir(parents=True)
    for name, content in cmd_scripts().items():
        (cmd / name).write_text(content, encoding="utf-8", newline="\n")

    cfg = proj / "config"
    cfg.mkdir()
    # privilege 必须是 JSON（fnpack 会解析，行式 run-as=package 会报 invalid character）
    (cfg / "privilege").write_text(
        json.dumps({"defaults": {"run-as": "package"},
                    "username": APPNAME, "groupname": APPNAME}),
        encoding="utf-8", newline="\n")
    (cfg / "resource").write_text(config_resource(), encoding="utf-8", newline="\n")

    wiz = proj / "wizard"
    wiz.mkdir()
    (wiz / "install").write_text(wizard_json("配置镜像地址"), encoding="utf-8", newline="\n")
    (wiz / "config").write_text(wizard_json("修改镜像地址"), encoding="utf-8", newline="\n")

    (proj / "manifest").write_text(manifest_text(version), encoding="utf-8", newline="\n")
    (proj / "ICON.PNG").write_bytes(make_icon_png(64))
    (proj / "ICON_256.PNG").write_bytes(make_icon_png(256))
    shutil.copy(ROOT / "LICENSE", proj / "LICENSE")
    return proj


# ---------------------------------------------------------------- 官方 fnpack 工具
def ensure_fnpack() -> Path:
    """优先用 PATH 里已有的 fnpack，否则下载官方二进制缓存到 tools/bin/。"""
    try:
        r = subprocess.run(["fnpack", "--help"], capture_output=True, timeout=15)
        if r.returncode == 0 or b"fnpack" in (r.stdout or r.stderr).lower():
            return Path("fnpack")
    except Exception:
        pass
    import os
    plat = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform_name())
    if plat is None:
        sys.exit("[x] 不支持的操作系统，无法下载 fnpack")
    cache = ROOT / "tools" / "bin" / ("fnpack.exe" if plat == "windows" else "fnpack")
    if cache.exists() and cache.stat().st_size > 100 * 1024:
        return cache
    url = FNPACK_URLS[plat]
    print(f"[i] 下载官方打包工具 fnpack {FNPACK_VERSION}（{plat}）...")
    cache.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    if len(data) < 100 * 1024:
        sys.exit("[x] fnpack 下载不完整，请检查网络后重试")
    cache.write_bytes(data)
    if plat != "windows":
        cache.chmod(cache.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return cache


def platform_name() -> str:
    if sys.platform.startswith("win"):
        return "Windows"
    if sys.platform.startswith("linux"):
        return "Linux"
    if sys.platform == "darwin":
        return "Darwin"
    return "?"


def patch_cmd_modes(fpk: Path):
    """fnpack 在 Windows 上会把 cmd/* 写成 0666，重打包补成 0755（LF 内容不变）。"""
    with tarfile.open(fpk, "r:gz") as zin:
        members = zin.getmembers()
        payload = {m.name: zin.extractfile(m).read() if m.isfile() else None for m in members}
    with tarfile.open(fpk, "w:gz") as zout:
        for m in members:
            m2 = m
            if m.name.startswith("cmd/") and m.isfile():
                m2.mode = 0o755
            if m.isdir():
                zout.addfile(m2)
            else:
                import io
                zout.addfile(m2, io.BytesIO(payload[m.name]))


def do_pack(version: str) -> None:
    stage = ROOT / ".fpk_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    out = ROOT / f"{APPNAME}-{version}.fpk"
    if out.exists():
        out.unlink()

    print("[1/3] 生成 fnpack 应用工程目录 ...")
    proj = build_project(stage, version)
    print(f"      {proj.relative_to(ROOT)}")

    print("[2/3] 调用官方 fnpack 打包 ...")
    fnpack = ensure_fnpack()
    r = subprocess.run([str(fnpack), "build", "--directory", str(proj)],
                       cwd=str(stage), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout or "", end="")
    if r.returncode != 0:
        print(r.stderr or "")
        sys.exit("[x] fnpack 打包失败（把上面的输出发给维护者排查）")

    candidates = [proj / f"{APPNAME}.fpk", proj / "build" / f"{APPNAME}.fpk", stage / f"{APPNAME}.fpk"]
    built = next((c for c in candidates if c.exists()), None)
    if built is None:
        found = list(stage.rglob("*.fpk"))
        if not found:
            sys.exit("[x] fnpack 未产出 .fpk，请检查输出")
        built = found[0]
    shutil.copy(built, out)
    print("[3/3] 修补 cmd/* 可执行权限（Windows fnpack 写 0666）...")
    patch_cmd_modes(out)
    shutil.rmtree(stage)

    with tarfile.open(out, "r:gz") as z:
        names = z.getnames()
    inner = tarfile.open(out, "r:gz")
    app_tgz = inner.extractfile("app.tgz").read()
    inner.close()
    md5 = hashlib.md5(app_tgz).hexdigest()
    print(f"[ok] 已生成 {out.name}（{out.stat().st_size / 1024 / 1024:.1f} MB，"
          f"{len(names)} 个顶层成员，app.tgz MD5 {md5[:8]}...）")
    print("[i] 安装：fnOS 应用中心 → 手动安装 → 选择该 .fpk（需先开启 Docker）")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
    do_pack(version)


if __name__ == "__main__":
    main()
