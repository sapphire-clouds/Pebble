"""
objects.py — ugit object store

Git stores everything as "objects" in .ugit/objects/.
Each object is identified by the SHA-1 hash of its content.
There are 3 types:
  - blob   : raw file content
  - tree   : a directory snapshot (list of blob/tree entries)
  - commit : a snapshot + metadata (message, parent, author)

This is called content-addressable storage:
the name of the file IS its content hash.
If two files have identical content, they share one blob. Free deduplication.
"""

import os
import hashlib
from pathlib import Path

GIT_DIR = ".ugit"


def get_repo_root():
    """Walk up from cwd until we find a .ugit directory."""
    path = Path.cwd()
    while path != path.parent:
        if (path / GIT_DIR).exists():
            return path
        path = path.parent
    raise RuntimeError("Not a ugit repository (no .ugit found)")


def object_path(sha: str) -> Path:
    """Objects are stored as .ugit/objects/<first2>/<remaining38>
    Same layout as real Git — avoids too many files in one directory."""
    root = get_repo_root()
    return root / GIT_DIR / "objects" / sha[:2] / sha[2:]


def hash_object(data: bytes, obj_type: str = "blob") -> str:
    """
    Store an object and return its SHA-1 hash.

    Format stored on disk:
        <type> <size>\0<content>
    e.g. for a blob:
        b"blob 13\0Hello, world!"

    This is exactly how real Git formats objects (before zlib compression).
    We skip zlib to keep things readable.
    """
    header = f"{obj_type} {len(data)}\0".encode()
    full = header + data
    sha = hashlib.sha1(full).hexdigest()

    path = object_path(sha)
    if not path.exists():                  # don't rewrite identical objects
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(full)

    return sha


def read_object(sha: str) -> tuple[str, bytes]:
    """
    Read an object by SHA-1. Returns (type, raw_content).
    Parses the '<type> <size>\\0<content>' header back out.
    """
    path = object_path(sha)
    if not path.exists():
        raise ValueError(f"Object not found: {sha}")

    full = path.read_bytes()
    null_idx = full.index(b"\0")
    header = full[:null_idx].decode()
    obj_type, _ = header.split(" ", 1)
    content = full[null_idx + 1:]
    return obj_type, content


# ── Tree encoding ──────────────────────────────────────────────────────────────
#
# A tree object represents one directory.
# Format (text, one entry per line):
#   <mode> <type> <sha>\t<name>
# e.g.:
#   100644 blob a1b2c3...\tREADME.md
#   040000 tree d4e5f6...\tsrc
#
# mode 100644 = regular file, 040000 = directory (same as real Git)

def encode_tree(entries: list[dict]) -> bytes:
    """
    entries: [{"mode": "100644", "type": "blob", "sha": "...", "name": "..."}, ...]
    Returns bytes ready to pass to hash_object(..., "tree").
    """
    lines = []
    for e in sorted(entries, key=lambda x: x["name"]):
        lines.append(f"{e['mode']} {e['type']} {e['sha']}\t{e['name']}")
    return "\n".join(lines).encode()


def decode_tree(data: bytes) -> list[dict]:
    """Parse tree bytes back into list of entry dicts."""
    entries = []
    for line in data.decode().splitlines():
        meta, name = line.split("\t", 1)
        mode, obj_type, sha = meta.split(" ", 2)
        entries.append({"mode": mode, "type": obj_type, "sha": sha, "name": name})
    return entries


# ── Commit encoding ────────────────────────────────────────────────────────────
#
# A commit object is plain text:
#   tree <tree_sha>
#   parent <parent_sha>        ← omitted for the very first commit
#   author <name>
#   timestamp <unix_time>
#
#   <blank line>
#   <commit message>

def encode_commit(tree_sha: str, message: str,
                  parent_sha: str = None, author: str = "ugit user") -> bytes:
    import time
    lines = [f"tree {tree_sha}"]
    if parent_sha:
        lines.append(f"parent {parent_sha}")
    lines.append(f"author {author}")
    lines.append(f"timestamp {int(time.time())}")
    lines.append("")                       # blank line separates header from message
    lines.append(message)
    return "\n".join(lines).encode()


def decode_commit(data: bytes) -> dict:
    """Parse commit bytes into a dict with keys: tree, parent, author, timestamp, message."""
    text = data.decode()
    header, _, message = text.partition("\n\n")
    result = {"parent": None, "message": message}
    for line in header.splitlines():
        key, _, val = line.partition(" ")
        result[key] = val
    return result
