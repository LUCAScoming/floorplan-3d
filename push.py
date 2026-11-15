"""户型装修设计 · Git 推送脚本

用法：
    python push.py [提交说明]      推送到远端（说明可省略，默认 "update 日期"）

说明：
    - 从项目根目录 .env 读取 GITHUB_TOKEN 与 GITHUB_REPO_URL（该文件已被 .gitignore 排除，切勿提交）
    - 仓库未初始化时自动 git init（分支 main）、关联 origin、完成首次提交与首次推送
    - 远端还没有 main 分支时（首次推送场景）自动跳过 pull --rebase
"""
import subprocess
import sys
from datetime import date
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
        git("remote", "add", "origin", url)
    else:
        git("remote", "set-url", "origin", url)   # 令牌更换后同步更新


def remote_has_branch(env: dict) -> bool:
    r = git("ls-remote", "--heads", "origin", BRANCH, check=False, show=False)
    return r.returncode == 0 and BRANCH in r.stdout


def commit_all(message: str) -> bool:
    """暂存全部改动并提交；没有改动时返回 False。"""
    git("add", "-A")
    r = git("status", "--porcelain", check=False, show=False)
    if not r.stdout.strip():
        print("[i] 没有需要提交的改动")
        return False
    git("commit", "-m", message or "update " + date.today().isoformat())
    return True


def main():
    env = load_env()
    message = " ".join(sys.argv[1:]).strip()
    ensure_repo(env)
    first_push = not remote_has_branch(env)
    if not first_push:
        git("pull", "--rebase", "origin", BRANCH)   # 先同步远端，避免冲突堆积
    commit_all(message)
    git("push", "-u", "origin", BRANCH)
    print(f"[ok] 已推送到 origin/{BRANCH}" + ("（首次推送）" if first_push else ""))


if __name__ == "__main__":
    main()
