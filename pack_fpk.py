"""户型装修设计 · FPK 打包脚本

FPK（FloorPlan pacKage）是本项目的自定义分发格式：本质是带清单的 ZIP 包，
扩展名用 .fpk，双击即可识别为"户型装修设计程序包"。

用法：
    python pack_fpk.py pack [输出文件]        打包程序为 .fpk（默认：户型装修设计_v日期.fpk）
    python pack_fpk.py unpack 包.fpk [-o 目录]  解包到目录（默认：与包同名的文件夹）
    python pack_fpk.py run 包.fpk             解包到临时目录并直接启动服务器

打包内容：index.html、libs/、app.py、requirements.txt、启动服务器.bat、README*、LICENSE、docs/screenshots/
自动排除：.env（含令牌，绝不打包）、plans/（用户方案）、.git、__pycache__、.playwright-cli、日志等。
"""
import json
import subprocess
import sys
import tempfile
import time
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 需要打包的文件 / 目录（相对根目录）
INCLUDE = [
    "index.html",
    "libs",
    "app.py",
    "requirements.txt",
    "启动服务器.bat",
    "README.md",
    "README.en.md",
    "LICENSE",
    ".gitignore",
    "push.py",
    "pull.py",
    "pack_fpk.py",
    Path("docs") / "screenshots",
]

# 打包时一律排除的文件 / 目录（INCLUDE 内也要排除）
EXCLUDE = {
    ".env", ".git", "__pycache__", ".playwright-cli",
    "plans", "server.log", ".codebuddy", "node_modules", ".idea", ".vscode",
}


def should_skip(rel: Path) -> bool:
    return any(p in EXCLUDE for p in rel.parts) or rel.suffix.lower() == ".pyc"


def collect_files() -> list:
    """收集 INCLUDE 中实际存在的文件，返回相对路径列表。"""
    files = []
    for item in INCLUDE:
        p = ROOT / item
        if p.is_file():
            files.append(Path(item))
        elif p.is_dir():
            files += [f.relative_to(ROOT) for f in p.rglob("*")
                      if f.is_file() and not should_skip(f.relative_to(ROOT))]
    return sorted(set(files))


def do_pack(out_name):
    files = collect_files()
    if not files:
        sys.exit("[x] 没有找到可打包的文件")
    out = Path(out_name) if out_name else ROOT / f"户型装修设计_v{time.strftime('%Y%m%d')}.fpk"
    if out.suffix.lower() != ".fpk":
        out = out.with_suffix(".fpk")
    manifest = {
        "format": "FPK",
        "name": "户型装修设计",
        "version": time.strftime("%Y-%m-%d"),
        "entry": "index.html",
        "server": "app.py",
        "files": [f.as_posix() for f in files],
        "packed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(ROOT / f, f.as_posix())
            print("  +", f.as_posix())
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"[ok] 已生成 {out.name}（{len(files) + 1} 个文件，{size_mb:.1f} MB）")


def open_fpk(path: Path):
    if not path.exists():
        sys.exit(f"[x] 找不到文件：{path}")
    if zipfile.is_zipfile(path):
        return zipfile.ZipFile(path)
    sys.exit("[x] 不是有效的 FPK 包（应为 ZIP 格式）")


def do_unpack(fpk: str, out_dir=None):
    target = Path(out_dir) if out_dir else Path(fpk).with_suffix("")
    with open_fpk(Path(fpk)) as z:
        names = [n for n in z.namelist() if not should_skip(Path(n))]
        z.extractall(target, members=names)
        print(f"[ok] 已解包 {len(names)} 个文件到：{target.resolve()}")


def do_run(fpk: str):
    """解包到临时目录并启动其中的 app.py（端口 8765，Ctrl+C 停止）。"""
    tmp = Path(tempfile.mkdtemp(prefix="fpk_"))
    do_unpack(fpk, str(tmp))
    if not (tmp / "app.py").exists():
        sys.exit("[x] 包内没有 app.py，无法启动服务器")
    print(f"[i] 已解包到临时目录 {tmp}，启动服务器（Ctrl+C 停止）...")
    webbrowser.open("http://localhost:8765")
    sys.exit(subprocess.call([sys.executable, str(tmp / "app.py")], cwd=tmp))


def main():
    argv = sys.argv[1:]
    action = argv[0].lower() if argv else ""
    if action == "pack":
        do_pack(argv[1] if len(argv) > 1 else None)
    elif action == "unpack":
        if len(argv) < 2:
            sys.exit(__doc__)
        out_dir = argv[argv.index("-o") + 1] if "-o" in argv else None
        do_unpack(argv[1], out_dir)
    elif action == "run":
        if len(argv) < 2:
            sys.exit(__doc__)
        do_run(argv[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
