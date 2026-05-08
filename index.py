"""
index.py — ugit staging area (the index)

The INDEX is what sits between your working directory and a commit.
When you run `git add`, you're writing to the index.
When you run `git commit`, the index is snapshotted into a tree object.

We store the index as a simple JSON file at .ugit/index:
  {
    "README.md":  "a1b2c3...",   ← path → blob SHA
    "src/main.py": "d4e5f6..."
  }

Real Git uses a binary format, but JSON is equivalent for our purposes
and means you can open .ugit/index in a text editor and read it.
"""

import json
from pathlib import Path
from objects import get_repo_root, GIT_DIR, hash_object


def index_path() -> Path:
    return get_repo_root() / GIT_DIR / "index"


def read_index() -> dict:
    """Returns {filepath_str: blob_sha} for everything currently staged."""
    p = index_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def write_index(index: dict):
    """Persist the index dict to disk."""
    index_path().write_text(json.dumps(index, indent=2, sort_keys=True))


def add_file(filepath: str):
    """
    Stage a single file.
    Reads the file, hashes it as a blob, stores the object, updates the index.
    filepath is relative to the repo root.
    """
    root = get_repo_root()
    full_path = root / filepath

    if not full_path.exists():
        raise FileNotFoundError(f"'{filepath}' not found")

    data = full_path.read_bytes()
    sha = hash_object(data, "blob")        # store the blob

    index = read_index()
    index[str(Path(filepath).as_posix())] = sha   # normalise to forward slashes
    write_index(index)
    return sha


def add_all(paths: list[str] = None):
    """
    Stage all files under the repo root (like `git add .`).
    Skips .ugit/ directory itself.
    """
    root = get_repo_root()
    index = read_index()

    targets = []
    if paths:
        targets = [root / p for p in paths]
    else:
        targets = [root]

    for target in targets:
        if target.is_file():
            files = [target]
        else:
            files = [f for f in target.rglob("*")
                     if f.is_file() and GIT_DIR not in f.parts]

        for f in files:
            rel = f.relative_to(root).as_posix()
            data = f.read_bytes()
            sha = hash_object(data, "blob")
            index[rel] = sha

    write_index(index)
    return index
