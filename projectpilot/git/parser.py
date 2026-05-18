from __future__ import annotations

import ast

from projectpilot.models.git_status import GitFileChange


def parse_branch_status(output: str) -> dict:
    branch: dict[str, str | int | None] = {
        "commit": None,
        "head": None,
        "upstream": None,
        "ahead": 0,
        "behind": 0,
    }
    for line in output.splitlines():
        if line.startswith("# branch.oid "):
            branch["commit"] = line.removeprefix("# branch.oid ").strip()
        elif line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ").strip()
            branch["head"] = None if head == "(detached)" else head
        elif line.startswith("# branch.upstream "):
            branch["upstream"] = line.removeprefix("# branch.upstream ").strip()
        elif line.startswith("# branch.ab "):
            ahead, behind = parse_ahead_behind(line.removeprefix("# branch.ab ").strip())
            branch["ahead"] = ahead
            branch["behind"] = behind
    return branch


def parse_status_entries(output: str) -> tuple[list[GitFileChange], list[str], list[str]]:
    changed: list[GitFileChange] = []
    untracked: list[str] = []
    conflicted: list[str] = []

    for line in output.splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("? "):
            untracked.append(decode_git_path(line[2:]))
            continue
        if line.startswith("! "):
            continue
        if line.startswith("1 "):
            change = parse_ordinary_change(line)
            if change:
                changed.append(change)
            continue
        if line.startswith("2 "):
            change = parse_rename_or_copy_change(line)
            if change:
                changed.append(change)
            continue
        if line.startswith("u "):
            path = decode_git_path(line.rsplit(" ", maxsplit=1)[-1])
            conflicted.append(path)

    return changed, untracked, conflicted


def parse_ahead_behind(text: str) -> tuple[int, int]:
    ahead = 0
    behind = 0
    for part in text.split():
        if part.startswith("+"):
            ahead = int(part[1:])
        elif part.startswith("-"):
            behind = int(part[1:])
    return ahead, behind


def parse_ordinary_change(line: str) -> GitFileChange | None:
    parts = line.split(" ", maxsplit=8)
    if len(parts) < 9:
        return None
    xy = parts[1]
    return GitFileChange(path=decode_git_path(parts[8]), index_status=xy[0], worktree_status=xy[1])


def parse_rename_or_copy_change(line: str) -> GitFileChange | None:
    parts = line.split(" ", maxsplit=9)
    if len(parts) < 10:
        return None
    xy = parts[1]
    path = decode_git_path(parts[9].split("\t", maxsplit=1)[0])
    return GitFileChange(path=path, index_status=xy[0], worktree_status=xy[1])


def parse_remotes(output: str) -> dict[str, list[str]]:
    remotes: dict[str, list[str]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, url = parts[0], parts[1]
        remotes.setdefault(name, [])
        if url not in remotes[name]:
            remotes[name].append(url)
    return remotes


def decode_git_path(raw_path: str) -> str:
    if not (raw_path.startswith('"') and raw_path.endswith('"')):
        return raw_path

    try:
        decoded = ast.literal_eval(raw_path)
    except (SyntaxError, ValueError):
        return raw_path.strip('"')

    try:
        return decoded.encode("latin1").decode("utf-8")
    except UnicodeError:
        return decoded
