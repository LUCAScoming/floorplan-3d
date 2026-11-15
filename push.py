"""户型装修设计 · Git 推送脚本

用法：
    python push.py [提交说明]      推送到远端（说明可省略，默认 "update 日期"）

说明：
    - 从项目根目录 .env 读取 GITHUB_TOKEN 与 GITHUB_REPO_URL（该文件已被 .gitignore 排除，切勿提交）
    - 仓库未初始化时自动 git init（分支 main）、关联 origin、完成首次提交与首次推送
    - 远端还没有 main 分支时（首次推送场景）自动跳过 pull --rebase
"""
import json
import subprocess
import sys
import urllib.request
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
        git("remote", "add", "origin", url, show=False)      # 带令牌的地址不回显
    else:
        git("remote", "set-url", "origin", url, show=False)  # 令牌更换后同步更新


def create_repo_if_missing(env: dict):
    """远端仓库不存在时，用令牌调用 GitHub API 自动创建（私有）。"""
    url = env["GITHUB_REPO_URL"].rstrip("/")
    repo = url.split("github.com/", 1)[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if "/" not in repo:
        print("[i] GITHUB_REPO_URL 不是 owner/repo 形式，跳过自动建仓")
        return
    name = repo.split("/")[-1]
    print(f"[i] 远端仓库 {repo} 不存在，尝试用 GitHub API 自动创建 ...")
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=json.dumps({"name": name, "private": True}).encode("utf-8"),
        headers={
            "Authorization": f"token {env['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "push.py",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        print(f"[ok] 已创建仓库 {body.get('full_name', repo)}（私有），如需公开请到 GitHub 仓库 Settings 里修改，或运行一次“改为公开”的 API 请求")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print("[i] 远端仓库已存在（422），继续推送")
        else:
            sys.exit(f"[x] 创建仓库失败（HTTP {e.code}）：{e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[x] 无法访问 GitHub API：{e.reason}")


def remote_has_branch(env: dict) -> bool:
    r = git("ls-remote", "--heads", "origin", BRANCH, check=False, show=False)
    if r.returncode != 0:                       # 仓库不存在 / 无权限
        create_repo_if_missing(env)
        r = git("ls-remote", "--heads", "origin", BRANCH, check=False, show=False)
        if r.returncode != 0:
            sys.exit("[x] 无法访问远端仓库，请检查 GITHUB_REPO_URL 与令牌权限（需要 repo 权限）")
    return BRANCH in r.stdout


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
    commit_all(message)                             # 先提交本地改动，pull --rebase 才不会因未提交内容拒绝执行
    first_push = not remote_has_branch(env)
    if not first_push:
        git("pull", "--rebase", "origin", BRANCH)   # 同步远端，避免冲突堆积
    git("push", "-u", "origin", BRANCH)
    print(f"[ok] 已推送到 origin/{BRANCH}" + ("（首次推送）" if first_push else ""))


if __name__ == "__main__":
    main()
