#!/usr/bin/env python3
"""Fake `gh` / `glab` for tests. Appends its argv to $FAKE_FORGE_LOG (JSON lines) and answers like the real CLIs:

    fake_forge.py issue view <ref> ...      → the JSON in $FAKE_FORGE_ISSUE (exit 1 with a message when unset)
    fake_forge.py pr|mr create ...          → prints the URL of the new request ($FAKE_FORGE_FAIL=1: exits 1)
"""
import json
import os
import sys


def main() -> int:
    argv = sys.argv[1:]
    log = os.environ.get("FAKE_FORGE_LOG")
    if log:
        with open(log, "a") as f:
            f.write(json.dumps(argv) + "\n")
    if argv[:2] == ["issue", "view"]:
        issue = os.environ.get("FAKE_FORGE_ISSUE")
        if not issue:
            print("GraphQL: Could not resolve to an Issue with the number of 999.", file=sys.stderr)
            return 1
        print(issue)
        return 0
    if len(argv) >= 2 and argv[1] == "create":
        if os.environ.get("FAKE_FORGE_FAIL"):
            print("a pull request for branch already exists", file=sys.stderr)
            return 1
        print("Creating request...\nhttps://forge.example/acme/app/-/merge_requests/7")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
