"""
refs.py — ugit references (branches + HEAD)

A "ref" is just a named pointer to a commit SHA.
Branches are refs. HEAD is a ref.

File layout under .ugit/:
  HEAD              ← contains either "ref: refs/heads/main"
                       or a raw SHA (detached HEAD)
  refs/
    heads/
      main          ← contains a commit SHA
      feature-x     ← another branch

This is identical to real Git's layout.
A branch is literally a one-line text file containing a 40-char SHA.
Creating a branch costs nothing — it's just writing a file.
"""

from pathlib import Path
from objects import get_repo_root, GIT_DIR


def refs_dir() -> Path:
    return get_repo_root() / GIT_DIR / "refs" / "heads"


def head_path() -> Path:
    return get_repo_root() / GIT_DIR / "HEAD"


# ── HEAD ───────────────────────────────────────────────────────────────────────

def get_head() -> str | None:
    """
    Returns the SHA that HEAD currently points to, or None if no commits yet.
    Handles both symbolic refs ("ref: refs/heads/main") and detached HEAD (raw SHA).
    """
    p = head_path()
    if not p.exists():
        return None

    content = p.read_text().strip()

    if content.startswith("ref: "):
        # Symbolic ref — follow it
        ref_path = get_repo_root() / GIT_DIR / content[5:]
        if not ref_path.exists():
            return None                    # branch exists but has no commits yet
        return ref_path.read_text().strip()
    else:
        # Detached HEAD — content is a raw SHA
        return content if content else None


def set_head(sha: str):
    """
    Advance HEAD (and the current branch) to point at sha.
    If HEAD is symbolic, update the branch file.
    If HEAD is detached, update HEAD directly.
    """
    p = head_path()
    content = p.read_text().strip() if p.exists() else "ref: refs/heads/main"

    if content.startswith("ref: "):
        ref_path = get_repo_root() / GIT_DIR / content[5:]
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(sha + "\n")
    else:
        p.write_text(sha + "\n")


def get_current_branch() -> str | None:
    """Returns branch name like 'main', or None if detached HEAD."""
    p = head_path()
    if not p.exists():
        return None
    content = p.read_text().strip()
    if content.startswith("ref: refs/heads/"):
        return content[len("ref: refs/heads/"):]
    return None                            # detached


# ── Branch operations ──────────────────────────────────────────────────────────

def create_branch(name: str, sha: str = None):
    """Create a new branch pointing at sha (defaults to current HEAD)."""
    if sha is None:
        sha = get_head()
        if sha is None:
            raise RuntimeError("Cannot create branch — no commits yet")

    branch_file = refs_dir() / name
    branch_file.parent.mkdir(parents=True, exist_ok=True)
    branch_file.write_text(sha + "\n")


def list_branches() -> list[str]:
    """Return all branch names."""
    d = refs_dir()
    if not d.exists():
        return []
    return [f.name for f in sorted(d.iterdir()) if f.is_file()]


def get_branch_sha(name: str) -> str | None:
    """Return the commit SHA a branch points to."""
    p = refs_dir() / name
    return p.read_text().strip() if p.exists() else None


def checkout_branch(name: str):
    """
    Switch HEAD to point at a different branch.
    Just rewrites the HEAD file — does NOT touch the working directory.
    (Working directory restore is handled in commands.py checkout)
    """
    branch_file = refs_dir() / name
    if not branch_file.exists():
        raise ValueError(f"Branch '{name}' does not exist")
    head_path().write_text(f"ref: refs/heads/{name}\n")
