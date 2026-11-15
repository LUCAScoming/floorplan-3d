"""户型装修设计 · Git 拉取脚本

用法：
    python pull.py    从远端拉取 main 分支并 rebase 到本地

说明：
    - 从项目根目录 .env 读取 GITHUB_TOKEN 与 GITHUB_REPO_URL（该文件已被 .gitignore 排除，切勿提交）
    - 本地未初始化 git 时自动 init 并关联 origin，首次拉取后建立本地 main 分支
    - 远端还没有 main 分支时提示无需拉取
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRANCH = "main"


def load_env() -> dict:
    env = {}
    p = ROOT / ".env"
    if not p.exists():
        sys.exit("[x] 未找到 .env，请先创建 GITHUB_TOKEN 与 GITHUB_REPO_URL 两项")
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    if not env.get("GITHUB_TOKEN") or not env.get("GITHUB_REPO_URL"):
        sys.exit("[x] .env 中缺少 GITHUB_TOKEN 或 GITHUB_REPO_URL")
    return env


def git(*args: str, check: bool = True, show: bool = True):
    """执行 git 命令，输出直通终端（show=False 时捕获输出）。"""
    if show:
        print("$", "git " + " ".join(args))
    r = subprocess.run(["git", *args], cwd=ROOT, shell=True,
                       capture_output=not show, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        if not show and (r.stdout or r.stderr):
            print(r.stdout or "", r.stderr or "")
        sys.exit(f"[x] git 命令失败（退出码 {r.returncode}）：git {' '.join(args)}")
    return r


def remote_url(env: dict) -> str:
    url = env["GITHUB_REPO_URL"].rstrip("/")
    token = env["GITHUB_TOKEN"]
    # 将 https://github.com/... 换成带令牌的地址，免去每次输密码
    if token and url.startswith("https://github.com/"):
        url = f"https://{token}@github.com/" + url.split("github.com/", 1)[1]
    return url


def ensure_repo(env: dict):
    """确保仓库已初始化并关联 origin（幂等）。"""
    if not (ROOT / ".git").exists():
        print("[i] 未初始化 git，执行 git init ...")
        git("init", "-b", BRANCH)
    url = remote_url(env)
    r = git("remote", "get-url", "origin", check=False, show=False)
    if r.returncode != 0:
        git("remote", "add", "origin", url, show=False)      # 带令牌的地址不回显
    else:
        git("remote", "set-url", "origin", url, show=False)  # 令牌更换后同步更新


def remote_has_branch(env: dict) -> bool:
    r = git("ls-remote", "--heads", "origin", BRANCH, check=False, show=False)
    if r.returncode != 0:
        sys.exit("[x] 无法访问远端仓库，请检查 GITHUB_REPO_URL 是否正确、令牌是否有该仓库权限")
    return BRANCH in r.stdout


def main():
    env = load_env()
    ensure_repo(env)
    if not remote_has_branch(env):
        print(f"[i] 远端还没有 {BRANCH} 分支，无需拉取")
        return
    git("pull", "--rebase", "origin", BRANCH)
    print(f"[ok] 已从 origin/{BRANCH} 拉取并 rebase")


if __name__ == "__main__":
    main()
