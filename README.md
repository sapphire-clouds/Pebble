#  pebble

> Git, but small. And you can read the whole thing on a Sunday afternoon.

A from-scratch implementation of Git's core internals in ~500 lines of Python. No external dependencies. No magic. Just the actual data model that Git has been quietly running on this whole time.

Built by [Jahnavi](https://github.com/sapphire-clouds) to answer the question: *"what actually happens when I type `git commit`?"*

---

```
$ python pebble.py init
Initialized empty pebble repository in /your/project/.pebble

$ python pebble.py add .
Staged 3 file(s)

$ python pebble.py commit -m "i have no idea what i'm doing"
[(main) 82b06660] i have no idea what i'm doing

$ python pebble.py log
commit 82b06660d69093f1d88e68d1e077b84583760a39 (HEAD -> main)
Author:    jahnavi
Timestamp: 1716000000

    i have no idea what i'm doing
```

---

## Why pebble?

Git stores everything as small, immutable objects — once written, they never change. They just sit there, content-addressed by their SHA-1 hash, being solid and reliable.

Like pebbles.


---

## What it can do

| Command | What happens |
|---|---|
| `pebble init` | Creates a `.pebble/` directory. You're now in a repo. |
| `pebble add <file>` | Stages a file. `add .` stages everything. |
| `pebble commit -m <msg>` | Snapshots the index. Advances HEAD. |
| `pebble status` | Shows what's staged, unstaged, and lurking untracked |
| `pebble log` | Walks commit history backwards from HEAD |
| `pebble diff` | Working directory vs what you last staged |
| `pebble diff --staged` | What you staged vs what you last committed |
| `pebble branch` | Lists branches. `*` marks where you are. |
| `pebble branch <name>` | Creates a branch. Costs nothing. Literally writes one file. |
| `pebble checkout <name>` | Switches branches and restores the working directory |

---

## How it actually works

This is the part that most Git tutorials skip. Here's the whole model:

### Everything is an object

Every piece of data — file content, directory snapshots, commits — is stored as an **object** under `.pebble/objects/`. Each object's filename is the SHA-1 hash of its content. This is called **content-addressable storage**, and it's the elegant idea the whole thing is built on.

There are exactly three kinds of objects:

---

**Blob** — a file's raw content. Nothing else. No filename, no metadata.

```
blob 13\0Hello, world!
```

If two files have identical content, they share one blob. Renaming a file doesn't create a new blob — only the tree changes. Free deduplication, by design.

---

**Tree** — a snapshot of one directory. Points to blobs (files) and other trees (subdirectories).

```
100644 blob a1b2c3...    README.md
100644 blob f7e8d2...    main.py
040000 tree d4e5f6...    src/
```

Recursive. Turtles all the way down.

---

**Commit** — a snapshot in time. Points at a tree, a parent commit, and a message.

```
tree   8f4a2b...
parent c3d1e9...
author jahnavi
timestamp 1716000000

finally fixed the bug (it was a semicolon)
```

Commits form a **linked list backwards through history**. `pebble log` just follows `parent` pointers until it hits the first commit (which has no parent).

---

### A branch is just a file

```
.pebble/refs/heads/main        →   "82b06660...\n"
.pebble/refs/heads/feature-x   →   "17968451...\n"
```

That's it. A branch is a text file containing a 40-character SHA. Creating a branch is O(1) — write a file. This is why Git says branching is "cheap." It is literally just writing a file.

---

### The index (staging area)

```json
{
  "README.md": "a1b2c3...",
  "src/main.py": "d4e5f6..."
}
```

`pebble add` hashes your file → stores the blob → writes the `path: sha` mapping here.  
`pebble commit` reads this, builds a tree object, wraps it in a commit, and advances HEAD.

The index is the thing that lets you stage some files but not others. It sits between your working directory and the commit history.

---

### What HEAD is

```
.pebble/HEAD  →  "ref: refs/heads/main\n"
```

HEAD points at your current branch. Your current branch points at a commit. That commit points at a tree. That tree points at blobs.

It's pointers all the way down. Which is also why `checkout` is fast — it just follows pointers and writes files.

---

## Project structure

```
pebble.py      ← CLI entry point, argument parsing
objects.py     ← blob / tree / commit storage and encoding
index.py       ← staging area
refs.py        ← HEAD and branch pointer management
commands.py    ← high-level logic that wires everything together
```

`.pebble/` layout after a few commits:

```
.pebble/
├── HEAD                        ← "ref: refs/heads/main"
├── index                       ← JSON staging area (human-readable)
├── objects/
│   ├── 82/
│   │   └── b06660d690...       ← a commit object
│   └── a1/
│       └── b2c3d4e5f6...       ← a blob object
└── refs/
    └── heads/
        ├── main                ← commit SHA
        └── feature-x          ← commit SHA
```

---

## Running it

Requires Python 3.8+. No `pip install` needed.

```bash
git clone https://github.com/YOURUSERNAME/pebble.git
cd pebble

# make a test directory to play in
mkdir demo && cd demo

python ../pebble.py init
python -c "open('README.md','w').write('# hello\n')"
python ../pebble.py add .
python ../pebble.py commit -m "first commit"
python ../pebble.py log

# try branching
python ../pebble.py branch dev
python ../pebble.py checkout dev
python -c "open('feature.txt','w').write('new thing\n')"
python ../pebble.py add .
python ../pebble.py commit -m "add feature"
python ../pebble.py log
```

> **Windows users:** use `python -c "open('file.txt','w').write('...')"` instead of PowerShell `echo` to avoid UTF-16 encoding issues. PowerShell's `echo` is sneaky like that.

---

## What's intentionally missing

| Feature | Notes |
|---|---|
| zlib compression | Real Git compresses objects on disk. Skipped here so you can open any object file in a text editor and read it. |
| Merge | Needs a lowest-common-ancestor walk + three-way diff. Solid weekend project extension. |
| Pack files | Git eventually bundles loose objects into one binary file for efficiency. Out of scope. |
| Remote / push / pull | A network protocol on top of the object model. The model here supports it as an extension. |
| .gitignore | Pattern matching. Straightforward to add. |

The core object model is complete. Everything above is a layer on top of it — the data structures don't need to change.

---

## Design notes

**SHA-1 for object identity** — same choice as real Git. Collision probability for a local repo is negligible. Git has moved toward SHA-256 for the same reason they switched; pebble is not a production system.

**JSON index instead of binary** — real Git's index format is binary. JSON is functionally identical and means `.pebble/index` is human-readable. Open it in VS Code after a `pebble add` and you'll see exactly what's staged.

**No zlib compression** — objects are larger on disk, but every object file is plain text. You can `cat` any file under `.pebble/objects/` and read it. That's the trade-off, and for a learning project it's the right one.

---

## Further reading

If this made Git make sense, these are worth your time:

- [Git Internals — Pro Git](https://git-scm.com/book/en/v2/Git-Internals-Plumbing-and-Porcelain) — the chapter that made this project click
- [Write Yourself a Git](https://wyag.thb.lt) — similar project, more complete implementation
- [Git from the Bottom Up](https://jwiegley.github.io/git-from-the-bottom-up/) — excellent conceptual walkthrough

---

<p align="center">made with curiosity by <a href="https://github.com/sapphire-clouds">jahnavi</a></p>