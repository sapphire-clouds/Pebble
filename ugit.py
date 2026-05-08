#!/usr/bin/env python3
"""
ugit — a Git implementation you can read in one sitting

Usage:
  ugit init
  ugit add <file> [<file> ...]   (use '.' to add everything)
  ugit commit -m <message>
  ugit status
  ugit log
  ugit diff
  ugit diff --staged
  ugit branch
  ugit branch <name>
  ugit checkout <branch>
"""

import sys
import os

# Make sure local modules are importable regardless of where ugit is called from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commands import (
    cmd_init, cmd_add, cmd_commit, cmd_log,
    cmd_status, cmd_diff, cmd_branch, cmd_checkout
)


def usage():
    print(__doc__)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        usage()

    cmd = args[0]

    try:
        if cmd == "init":
            path = args[1] if len(args) > 1 else "."
            cmd_init(path)

        elif cmd == "add":
            if len(args) < 2:
                print("Usage: ugit add <file> [<file> ...]")
                sys.exit(1)
            cmd_add(args[1:])

        elif cmd == "commit":
            if "-m" not in args:
                print("Usage: ugit commit -m <message>")
                sys.exit(1)
            msg_idx = args.index("-m") + 1
            if msg_idx >= len(args):
                print("Error: no message after -m")
                sys.exit(1)
            message = args[msg_idx]
            author = None
            if "--author" in args:
                author = args[args.index("--author") + 1]
            cmd_commit(message, author)

        elif cmd == "log":
            cmd_log()

        elif cmd == "status":
            cmd_status()

        elif cmd == "diff":
            staged = "--staged" in args or "--cached" in args
            cmd_diff(staged=staged)

        elif cmd == "branch":
            name = args[1] if len(args) > 1 else None
            cmd_branch(name)

        elif cmd == "checkout":
            if len(args) < 2:
                print("Usage: ugit checkout <branch>")
                sys.exit(1)
            cmd_checkout(args[1])

        else:
            print(f"ugit: unknown command '{cmd}'")
            usage()

    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
