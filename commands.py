"""
commands.py — ugit high-level commands

Each function here maps to one CLI command:
  ugit init
  ugit add <file> [<file> ...]
  ugit commit -m <message>
  ugit log
  ugit status
  ugit diff
  ugit branch [<name>]
  ugit checkout <branch>

The separation of concerns:
  objects.py  → raw storage (hashing, reading, writing blobs/trees/commits)
  index.py    → staging area
  refs.py     → branch and HEAD pointers
  commands.py → user-facing logic that wires the above together
"""

import os
from pathlib import Path
from objects import (
    GIT_DIR, get_repo_root, hash_object, read_object,
    encode_tree, decode_tree, encode_commit, decode_commit
)
from index import read_index, write_index, add_all
from refs import (
    get_head, set_head, get_current_branch,
    create_branch, list_branches, get_branch_sha, checkout_branch
)


# ── init ───────────────────────────────────────────────────────────────────────

def cmd_init(path: str = "."):
    """
    Create a new ugit repository.
    Creates .ugit/ with the same subdirectory layout as real Git.
    """
    root = Path(path).resolve()
    git_dir = root / GIT_DIR

    if git_dir.exists():
        print(f"Reinitialized existing ugit repository in {git_dir}")
        return

    (git_dir / "objects").mkdir(parents=True)
    (git_dir / "refs" / "heads").mkdir(parents=True)

    # HEAD starts pointing at 'main' (branch doesn't exist yet — that's fine)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

    print(f"Initialized empty ugit repository in {git_dir}")


# ── add ────────────────────────────────────────────────────────────────────────

def cmd_add(paths: list[str]):
    """
    Stage files for the next commit.
    '.' means add everything.
    """
    if paths == ["."]:
        index = add_all()
        print(f"Staged {len(index)} file(s)")
    else:
        from index import add_file
        for p in paths:
            sha = add_file(p)
            print(f"add '{p}' → {sha[:8]}")


# ── commit ─────────────────────────────────────────────────────────────────────

def _build_tree_from_index(index: dict) -> str:
    """
    Convert the flat {path: sha} index into a nested tree of tree objects.

    Example index:
      {"README.md": "aaa", "src/main.py": "bbb", "src/util.py": "ccc"}

    Produces tree objects:
      tree for "src/" containing main.py and util.py
      root tree containing README.md and the src/ subtree

    This is recursive: each directory becomes its own tree object.
    """
    # Group entries by their top-level directory component
    # {"": [("README.md", "aaa", "blob")], "src": [("main.py","bbb","blob"), ...]}
    dirs: dict[str, list] = {}

    for filepath, sha in index.items():
        parts = filepath.split("/")
        if len(parts) == 1:
            dirs.setdefault("", []).append((parts[0], sha, "blob"))
        else:
            top = parts[0]
            rest = "/".join(parts[1:])
            dirs.setdefault(top, []).append((rest, sha, "blob"))

    # Recursively build subtrees
    root_entries = []
    for name, children in dirs.items():
        if name == "":
            # Direct files in root
            for fname, sha, _ in children:
                root_entries.append({"mode": "100644", "type": "blob",
                                     "sha": sha, "name": fname})
        else:
            # Subdirectory — recurse by building a sub-index
            sub_index = {path: sha for path, sha, _ in children}
            sub_tree_sha = _build_tree_from_index(sub_index)
            root_entries.append({"mode": "040000", "type": "tree",
                                  "sha": sub_tree_sha, "name": name})

    tree_data = encode_tree(root_entries)
    return hash_object(tree_data, "tree")


def cmd_commit(message: str, author: str = None):
    """
    Snapshot the index as a commit.
    1. Build a tree from the current index
    2. Create a commit object pointing at that tree + the current HEAD
    3. Advance HEAD to the new commit
    """
    if not author:
        author = os.environ.get("UGIT_AUTHOR", "ugit user")

    index = read_index()
    if not index:
        print("Nothing to commit (index is empty — run 'ugit add' first)")
        return

    tree_sha = _build_tree_from_index(index)
    parent_sha = get_head()                # None for first commit

    commit_data = encode_commit(tree_sha, message, parent_sha, author)
    commit_sha = hash_object(commit_data, "commit")

    set_head(commit_sha)

    branch = get_current_branch()
    label = f"({branch})" if branch else "(detached HEAD)"
    print(f"[{label} {commit_sha[:8]}] {message}")
    return commit_sha


# ── log ────────────────────────────────────────────────────────────────────────

def cmd_log(max_commits: int = 20):
    """
    Walk the commit chain from HEAD back to the first commit.
    Each commit stores its parent SHA — this forms a linked list.
    """
    sha = get_head()
    if sha is None:
        print("No commits yet")
        return

    count = 0
    while sha and count < max_commits:
        obj_type, data = read_object(sha)
        if obj_type != "commit":
            break
        c = decode_commit(data)

        branch = ""
        current = get_head()
        if current == sha:
            b = get_current_branch()
            branch = f" (HEAD -> {b})" if b else " (HEAD)"

        print(f"\033[33mcommit {sha}{branch}\033[0m")
        print(f"Author:    {c.get('author', '?')}")
        print(f"Timestamp: {c.get('timestamp', '?')}")
        print()
        print(f"    {c['message']}")
        print()

        sha = c.get("parent")
        count += 1


# ── status ─────────────────────────────────────────────────────────────────────

def _tree_to_flat(tree_sha: str, prefix: str = "") -> dict:
    """Recursively flatten a tree into {path: blob_sha}."""
    result = {}
    _, data = read_object(tree_sha)
    for entry in decode_tree(data):
        full = f"{prefix}{entry['name']}" if not prefix else f"{prefix}/{entry['name']}"
        if entry["type"] == "blob":
            result[full] = entry["sha"]
        elif entry["type"] == "tree":
            result.update(_tree_to_flat(entry["sha"], full))
    return result


def cmd_status():
    """
    Compare three things:
      1. Last commit (HEAD tree)
      2. Index (staged)
      3. Working directory (actual files)

    Shows:
      - Changes staged for commit (index vs HEAD)
      - Changes not staged (working dir vs index)
      - Untracked files (not in index at all)
    """
    root = get_repo_root()
    index = read_index()
    branch = get_current_branch() or "detached HEAD"
    print(f"On branch {branch}")

    # HEAD tree
    head_sha = get_head()
    committed = {}
    if head_sha:
        _, commit_data = read_object(head_sha)
        c = decode_commit(commit_data)
        committed = _tree_to_flat(c["tree"])

    # Staged vs committed
    staged_new, staged_modified, staged_deleted = [], [], []
    for path, sha in index.items():
        if path not in committed:
            staged_new.append(path)
        elif committed[path] != sha:
            staged_modified.append(path)
    for path in committed:
        if path not in index:
            staged_deleted.append(path)

    if staged_new or staged_modified or staged_deleted:
        print("\nChanges to be committed:")
        for p in sorted(staged_new):      print(f"  \033[32mnew file:   {p}\033[0m")
        for p in sorted(staged_modified): print(f"  \033[32mmodified:   {p}\033[0m")
        for p in sorted(staged_deleted):  print(f"  \033[32mdeleted:    {p}\033[0m")

    # Working dir vs index
    unstaged, untracked = [], []
    all_files = [f.relative_to(root).as_posix()
                 for f in root.rglob("*")
                 if f.is_file() and GIT_DIR not in f.parts]

    for rel in all_files:
        if rel in index:
            current_sha = hash_object((root / rel).read_bytes(), "blob")
            if current_sha != index[rel]:
                unstaged.append(rel)
        else:
            untracked.append(rel)

    if unstaged:
        print("\nChanges not staged for commit:")
        for p in sorted(unstaged): print(f"  \033[31mmodified:   {p}\033[0m")

    if untracked:
        print("\nUntracked files:")
        for p in sorted(untracked): print(f"  \033[90m{p}\033[0m")

    if not any([staged_new, staged_modified, staged_deleted, unstaged, untracked]):
        print("nothing to commit, working tree clean")


# ── diff ───────────────────────────────────────────────────────────────────────

def _simple_diff(old_lines: list[str], new_lines: list[str],
                 filename: str) -> list[str]:
    """
    Minimal line-by-line diff using Python's difflib.
    Returns unified diff lines — same format as `git diff`.
    """
    import difflib
    return list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    ))


def cmd_diff(staged: bool = False):
    """
    staged=False : working directory vs index  (like `git diff`)
    staged=True  : index vs last commit        (like `git diff --staged`)
    """
    root = get_repo_root()
    index = read_index()

    if staged:
        # Compare index to HEAD commit
        head_sha = get_head()
        committed = {}
        if head_sha:
            _, commit_data = read_object(head_sha)
            c = decode_commit(commit_data)
            committed = _tree_to_flat(c["tree"])

        for path, sha in index.items():
            old_content = ""
            if path in committed:
                _, blob_data = read_object(committed[path])
                old_content = blob_data.decode(errors="replace")
            _, new_blob = read_object(sha)
            new_content = new_blob.decode(errors="replace")

            lines = _simple_diff(old_content.splitlines(keepends=True),
                                  new_content.splitlines(keepends=True), path)
            _print_diff(lines)
    else:
        # Compare working directory to index
        for path, sha in index.items():
            full = root / path
            if not full.exists():
                print(f"deleted: {path}")
                continue
            _, blob_data = read_object(sha)
            old_content = blob_data.decode(errors="replace")
            new_content = full.read_text(errors="replace")
            if old_content != new_content:
                lines = _simple_diff(old_content.splitlines(keepends=True),
                                      new_content.splitlines(keepends=True), path)
                _print_diff(lines)


def _print_diff(lines: list[str]):
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            print(f"\033[1m{line}\033[0m")
        elif line.startswith("+"):
            print(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            print(f"\033[31m{line}\033[0m")
        elif line.startswith("@@"):
            print(f"\033[36m{line}\033[0m")
        else:
            print(line)


# ── branch ─────────────────────────────────────────────────────────────────────

def cmd_branch(name: str = None):
    """
    No args  → list all branches
    With name → create a new branch at current HEAD
    """
    if name is None:
        current = get_current_branch()
        for b in list_branches():
            prefix = "* " if b == current else "  "
            print(f"{prefix}{b}")
    else:
        create_branch(name)
        print(f"Created branch '{name}'")


# ── checkout ───────────────────────────────────────────────────────────────────

def cmd_checkout(branch_name: str):
    """
    Switch to a different branch.
    1. Move HEAD to point at the branch
    2. Restore the working directory to match that branch's commit tree
    3. Update the index to match
    """
    # Verify branch exists
    sha = get_branch_sha(branch_name)
    if sha is None:
        raise ValueError(f"Branch '{branch_name}' not found")

    root = get_repo_root()

    # Read target tree
    _, commit_data = read_object(sha)
    c = decode_commit(commit_data)
    target_files = _tree_to_flat(c["tree"])

    # Restore files
    for path, blob_sha in target_files.items():
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        _, data = read_object(blob_sha)
        full.write_bytes(data)

    # Remove files that exist in current branch but not target
    index = read_index()
    for path in index:
        if path not in target_files:
            full = root / path
            if full.exists():
                full.unlink()

    # Update index and HEAD
    write_index(target_files)
    checkout_branch(branch_name)
    print(f"Switched to branch '{branch_name}'")
