"""
vps-manager/utils/git.py
─────────────────────────────────────────────────────────────────
Professional Git manager for vps-manager.
Handles: repo linking, branch management, commits, checkout,
         status, diff, log, stash, remote sync, rm --cached.
All public functions return (ok: bool, message/data).
"""

import os
import subprocess
import re
from typing import Tuple, List, Optional


# ─── Low-level helpers ────────────────────────────────────────────────────────

def _run(args: list, cwd: str = None, env: dict = None) -> Tuple[bool, str]:
    """Run a git command. Returns (success, combined output)."""
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "Command timed out (30s)"
    except FileNotFoundError:
        return False, "git not found. Install: sudo apt install git"
    except Exception as e:
        return False, str(e)


def git_available() -> bool:
    ok, _ = _run(["git", "--version"])
    return ok


def git_version() -> str:
    ok, out = _run(["git", "--version"])
    return out if ok else "not installed"


# ─── Repo detection ───────────────────────────────────────────────────────────

def is_git_repo(path: str) -> bool:
    """Check if path is inside a git repo."""
    ok, _ = _run(["git", "rev-parse", "--git-dir"], cwd=path)
    return ok


def get_repo_root(path: str) -> Optional[str]:
    """Return the root of the git repo containing path."""
    ok, out = _run(["git", "rev-parse", "--show-toplevel"], cwd=path)
    return out if ok else None


def init_repo(path: str) -> Tuple[bool, str]:
    """Initialize a new git repo at path."""
    os.makedirs(path, exist_ok=True)
    return _run(["git", "init"], cwd=path)


# ─── Branch management ────────────────────────────────────────────────────────

def list_branches(path: str) -> Tuple[bool, List[dict]]:
    """
    Returns (ok, list of {name, current, remote}).
    """
    ok, out = _run(["git", "branch", "-a", "--format=%(refname:short) %(HEAD)"], cwd=path)
    if not ok:
        return False, []
    branches = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.rsplit(" ", 1)
        name    = parts[0].strip()
        current = len(parts) > 1 and parts[1] == "*"
        is_remote = name.startswith("remotes/") or name.startswith("origin/")
        branches.append({"name": name, "current": current, "remote": is_remote})
    return True, branches


def current_branch(path: str) -> str:
    ok, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    return out if ok else "unknown"


def checkout_branch(path: str, branch: str, create: bool = False) -> Tuple[bool, str]:
    if create:
        return _run(["git", "checkout", "-b", branch], cwd=path)
    return _run(["git", "checkout", branch], cwd=path)


def create_branch(path: str, branch: str, from_branch: str = None) -> Tuple[bool, str]:
    if from_branch:
        return _run(["git", "checkout", "-b", branch, from_branch], cwd=path)
    return _run(["git", "checkout", "-b", branch], cwd=path)


def delete_branch(path: str, branch: str, force: bool = False) -> Tuple[bool, str]:
    flag = "-D" if force else "-d"
    return _run(["git", "branch", flag, branch], cwd=path)


def merge_branch(path: str, branch: str) -> Tuple[bool, str]:
    return _run(["git", "merge", branch, "--no-edit"], cwd=path)


def rename_branch(path: str, old: str, new: str) -> Tuple[bool, str]:
    return _run(["git", "branch", "-m", old, new], cwd=path)


# ─── Commit management ────────────────────────────────────────────────────────

def get_log(path: str, branch: str = None, limit: int = 50) -> Tuple[bool, List[dict]]:
    """
    Returns list of commit dicts: {hash, short_hash, author, date, message}.
    """
    args = ["git", "log",
            "--format=%H\x1f%h\x1f%an\x1f%ad\x1f%s",
            "--date=short",
            f"-{limit}"]
    if branch:
        args.append(branch)
    ok, out = _run(args, cwd=path)
    if not ok:
        return False, []
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 4)
        if len(parts) == 5:
            commits.append({
                "hash":       parts[0],
                "short_hash": parts[1],
                "author":     parts[2],
                "date":       parts[3],
                "message":    parts[4],
            })
    return True, commits


def checkout_commit(path: str, commit_hash: str) -> Tuple[bool, str]:
    """Detach HEAD at a specific commit."""
    return _run(["git", "checkout", commit_hash], cwd=path)


def get_commit_diff(path: str, commit_hash: str) -> Tuple[bool, str]:
    return _run(["git", "show", "--stat", commit_hash], cwd=path)


def get_commit_full_diff(path: str, commit_hash: str) -> Tuple[bool, str]:
    return _run(["git", "show", commit_hash], cwd=path)


# ─── Working tree ────────────────────────────────────────────────────────────

def status(path: str) -> Tuple[bool, str]:
    return _run(["git", "status"], cwd=path)


def status_short(path: str) -> Tuple[bool, str]:
    return _run(["git", "status", "--short"], cwd=path)


def diff(path: str, staged: bool = False) -> Tuple[bool, str]:
    args = ["git", "diff", "--stat"]
    if staged:
        args.append("--cached")
    return _run(args, cwd=path)


def stage_all(path: str) -> Tuple[bool, str]:
    return _run(["git", "add", "-A"], cwd=path)


def stage_file(path: str, filepath: str) -> Tuple[bool, str]:
    return _run(["git", "add", filepath], cwd=path)


def unstage_file(path: str, filepath: str) -> Tuple[bool, str]:
    return _run(["git", "restore", "--staged", filepath], cwd=path)


def commit(path: str, message: str, author: str = None) -> Tuple[bool, str]:
    args = ["git", "commit", "-m", message]
    if author:
        args.extend(["--author", author])
    return _run(args, cwd=path)


def commit_amend(path: str, message: str = None) -> Tuple[bool, str]:
    args = ["git", "commit", "--amend"]
    if message:
        args.extend(["-m", message])
    else:
        args.append("--no-edit")
    return _run(args, cwd=path)


# ─── Stash ────────────────────────────────────────────────────────────────────

def stash_list(path: str) -> Tuple[bool, List[dict]]:
    ok, out = _run(["git", "stash", "list",
                    "--format=%gd\x1f%s\x1f%cr"], cwd=path)
    if not ok:
        return False, []
    stashes = []
    for line in out.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            stashes.append({
                "ref":     parts[0],
                "message": parts[1],
                "when":    parts[2],
            })
    return True, stashes


def stash_push(path: str, message: str = "") -> Tuple[bool, str]:
    args = ["git", "stash", "push"]
    if message:
        args.extend(["-m", message])
    return _run(args, cwd=path)


def stash_pop(path: str, ref: str = None) -> Tuple[bool, str]:
    args = ["git", "stash", "pop"]
    if ref:
        args.append(ref)
    return _run(args, cwd=path)


def stash_drop(path: str, ref: str) -> Tuple[bool, str]:
    return _run(["git", "stash", "drop", ref], cwd=path)


def stash_show(path: str, ref: str) -> Tuple[bool, str]:
    return _run(["git", "stash", "show", "-p", ref], cwd=path)


# ─── Remote management ───────────────────────────────────────────────────────

def list_remotes(path: str) -> Tuple[bool, List[dict]]:
    ok, out = _run(["git", "remote", "-v"], cwd=path)
    if not ok:
        return False, []
    seen = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            url  = parts[1]
            if name not in seen:
                seen[name] = url
    return True, [{"name": k, "url": v} for k, v in seen.items()]


def add_remote(path: str, name: str, url: str) -> Tuple[bool, str]:
    return _run(["git", "remote", "add", name, url], cwd=path)


def remove_remote(path: str, name: str) -> Tuple[bool, str]:
    return _run(["git", "remote", "remove", name], cwd=path)


def set_remote_url(path: str, name: str, url: str) -> Tuple[bool, str]:
    return _run(["git", "remote", "set-url", name, url], cwd=path)


def fetch(path: str, remote: str = "origin") -> Tuple[bool, str]:
    return _run(["git", "fetch", remote, "--prune"], cwd=path)


def pull(path: str, remote: str = "origin", branch: str = None) -> Tuple[bool, str]:
    args = ["git", "pull", remote]
    if branch:
        args.append(branch)
    return _run(args, cwd=path)


def push(path: str, remote: str = "origin", branch: str = None,
         set_upstream: bool = False, force: bool = False) -> Tuple[bool, str]:
    args = ["git", "push", remote]
    if branch:
        args.append(branch)
    if set_upstream:
        args.extend(["-u"])
        args = ["git", "push", "-u", remote, branch or current_branch(path)]
    if force:
        args.append("--force-with-lease")
    return _run(args, cwd=path)


# ─── rm --cached (untrack files) ────────────────────────────────────────────

def rm_cached(path: str, pattern: str = ".", recursive: bool = True) -> Tuple[bool, str]:
    """
    Remove file(s) from git index without deleting from disk.
    Pattern can be a specific file or '.' for all.
    """
    args = ["git", "rm", "--cached"]
    if recursive:
        args.append("-r")
    args.append(pattern)
    return _run(args, cwd=path)


def create_gitignore(path: str, patterns: List[str]) -> Tuple[bool, str]:
    """Append patterns to .gitignore."""
    gi_path = os.path.join(path, ".gitignore")
    try:
        existing = ""
        if os.path.exists(gi_path):
            with open(gi_path, "r") as f:
                existing = f.read()
        new_patterns = [p for p in patterns if p not in existing]
        if not new_patterns:
            return True, ".gitignore already contains all patterns"
        with open(gi_path, "a") as f:
            f.write("\n" + "\n".join(new_patterns) + "\n")
        return True, f"Added {len(new_patterns)} pattern(s) to .gitignore"
    except Exception as e:
        return False, str(e)


# ─── Tags ────────────────────────────────────────────────────────────────────

def list_tags(path: str) -> Tuple[bool, List[str]]:
    ok, out = _run(["git", "tag", "-l", "--sort=-version:refname"], cwd=path)
    if not ok:
        return False, []
    return True, [t for t in out.splitlines() if t.strip()]


def create_tag(path: str, name: str, message: str = "", commit: str = "") -> Tuple[bool, str]:
    args = ["git", "tag"]
    if message:
        args.extend(["-a", name, "-m", message])
    else:
        args.append(name)
    if commit:
        args.append(commit)
    return _run(args, cwd=path)


def delete_tag(path: str, name: str) -> Tuple[bool, str]:
    return _run(["git", "tag", "-d", name], cwd=path)


# ─── Config ────────────────────────────────────────────────────────────────────

def get_git_config(path: str) -> dict:
    user_name  = _run(["git", "config", "user.name"],  cwd=path)[1]
    user_email = _run(["git", "config", "user.email"], cwd=path)[1]
    return {"user.name": user_name, "user.email": user_email}


def set_git_config(path: str, name: str, email: str) -> Tuple[bool, str]:
    ok1, m1 = _run(["git", "config", "user.name",  name],  cwd=path)
    ok2, m2 = _run(["git", "config", "user.email", email], cwd=path)
    if ok1 and ok2:
        return True, "Git config updated"
    return False, f"{m1}  {m2}"


# ─── Stats & info ────────────────────────────────────────────────────────────

def repo_info(path: str) -> dict:
    """Gather comprehensive repo info."""
    root   = get_repo_root(path) or path
    branch = current_branch(root)
    ok_st, st_short = status_short(root)
    changed = len([l for l in st_short.splitlines() if l.strip()]) if ok_st else 0

    ok_log, commits = get_log(root, limit=1)
    last_commit = commits[0] if (ok_log and commits) else None

    ok_rem, remotes = list_remotes(root)
    ok_br,  branches = list_branches(root)

    local_branches  = [b for b in branches if not b["remote"]] if ok_br else []
    remote_branches = [b for b in branches if b["remote"]]     if ok_br else []

    return {
        "root":            root,
        "branch":          branch,
        "changed_files":   changed,
        "last_commit":     last_commit,
        "remotes":         remotes if ok_rem else [],
        "local_branches":  local_branches,
        "remote_branches": remote_branches,
        "status_short":    st_short if ok_st else "",
    }