from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from projectpilot.git.analyzer import analyze_status
from projectpilot.git.executor import get_diff, get_log, run_fetch
from projectpilot.git.inspector import inspect_repository
from projectpilot.git.recommender import build_recommendations
from projectpilot.git.reporter import render_markdown_report, save_markdown_report
from projectpilot.models.git_status import GitStatus


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    try:
        return args.handler(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="projectpilot",
        description="ProjectPilot intelligent Git assistant.",
    )
    subparsers = parser.add_subparsers(dest="domain")

    git_parser = subparsers.add_parser("git", help="Inspect and explain Git repository state.")
    git_subparsers = git_parser.add_subparsers(dest="git_command")

    for name, help_text, handler in [
        ("status", "Show structured Git status.", handle_git_status),
        ("explain", "Explain the current Git state in plain language.", handle_git_explain),
        ("suggest", "Suggest safe next Git actions.", handle_git_suggest),
        ("report", "Generate a Markdown Git status report.", handle_git_report),
    ]:
        command = git_subparsers.add_parser(name, help=help_text)
        command.add_argument(
            "path",
            nargs="?",
            default=".",
            help="Repository path. Defaults to the current directory.",
        )
        command.add_argument(
            "--json",
            action="store_true",
            help="Print machine-readable JSON instead of text where supported.",
        )
        command.set_defaults(handler=handler)

    diff_command = git_subparsers.add_parser("diff", help="Show Git diff output with safe defaults.")
    add_path_argument(diff_command)
    diff_command.add_argument("--cached", action="store_true", help="Show staged changes.")
    diff_command.add_argument("--stat", action="store_true", help="Show diff statistics.")
    diff_command.add_argument("--name-only", action="store_true", help="Show only changed file names.")
    diff_command.set_defaults(handler=handle_git_diff)

    log_command = git_subparsers.add_parser("log", help="Show recent Git history.")
    add_path_argument(log_command)
    log_command.add_argument("-n", "--limit", type=int, default=10, help="Number of commits to show, from 1 to 100.")
    log_command.set_defaults(handler=handle_git_log)

    fetch_command = git_subparsers.add_parser("fetch", help="Fetch remote refs without changing the working tree.")
    add_path_argument(fetch_command)
    fetch_command.add_argument("--remote", help="Remote name to fetch. Defaults to all remotes.")
    fetch_command.add_argument("--prune", action="store_true", help="Prune deleted remote-tracking branches.")
    fetch_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    fetch_command.set_defaults(handler=handle_git_fetch)

    return parser


def add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository path. Defaults to the current directory.",
    )


def handle_git_status(args: argparse.Namespace) -> int:
    status = inspect_repository(Path(args.path))
    analysis = analyze_status(status)

    if args.json:
        print(json.dumps(status.to_dict() | {"analysis": analysis.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    print_status(status, analysis)
    return 0


def handle_git_explain(args: argparse.Namespace) -> int:
    status = inspect_repository(Path(args.path))
    analysis = analyze_status(status)

    if args.json:
        print(json.dumps({"explanation": analysis.explanation, "analysis": analysis.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    print(analysis.explanation)
    return 0


def handle_git_suggest(args: argparse.Namespace) -> int:
    status = inspect_repository(Path(args.path))
    analysis = analyze_status(status)
    recommendations = build_recommendations(status, analysis)

    if args.json:
        print(
            json.dumps(
                {
                    "risk": analysis.risk.to_dict(),
                    "recommendations": [item.to_dict() for item in recommendations],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print_suggestions(status, analysis, recommendations)
    return 0


def handle_git_report(args: argparse.Namespace) -> int:
    status = inspect_repository(Path(args.path))
    analysis = analyze_status(status)
    recommendations = build_recommendations(status, analysis)
    report = render_markdown_report(status, analysis, recommendations)
    report_path = save_markdown_report(status.repo_path, report)

    if args.json:
        print(json.dumps({"report_path": str(report_path)}, ensure_ascii=False, indent=2))
        return 0

    print(f"Git status report written to: {report_path}")
    return 0


def handle_git_diff(args: argparse.Namespace) -> int:
    result = get_diff(
        Path(args.path),
        cached=args.cached,
        stat=args.stat,
        name_only=args.name_only,
    )
    print(result.stdout.rstrip() or "No diff.")
    return 0


def handle_git_log(args: argparse.Namespace) -> int:
    result = get_log(Path(args.path), limit=args.limit)
    print(result.stdout.rstrip() or "No commits.")
    return 0


def handle_git_fetch(args: argparse.Namespace) -> int:
    result, status = run_fetch(Path(args.path), remote=args.remote, prune=args.prune)
    analysis = analyze_status(status)

    if args.json:
        print(
            json.dumps(
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "status": status.to_dict(),
                    "analysis": analysis.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    print("Fetch completed. Working tree files were not modified.")
    print()
    print_status(status, analysis)
    return 0


def print_status(status: GitStatus, analysis) -> None:
    print(f"Repository: {status.repo_path}")
    print(f"Branch: {status.branch or '(detached HEAD)'}")
    print(f"Commit: {status.commit or 'unknown'}")
    print(f"Upstream: {status.upstream or 'not configured'}")
    print(f"Ahead/Behind: +{status.ahead} / -{status.behind}")
    print(f"State: {status.state}")
    print(f"Clean: {'yes' if status.is_clean else 'no'}")
    print(f"Risk: {analysis.risk.level}")
    print()
    print_file_group("Staged", status.staged_files)
    print_file_group("Unstaged", status.unstaged_files)
    print_file_group("Untracked", status.untracked_files)
    print_file_group("Conflicted", status.conflicted_files)


def print_file_group(title: str, files: list[str]) -> None:
    print(f"{title}: {len(files)}")
    for path in files:
        print(f"  - {path}")


def print_suggestions(status: GitStatus, analysis, recommendations) -> None:
    print(analysis.explanation)
    print()
    print(f"Risk: {analysis.risk.level}")
    for reason in analysis.risk.reasons:
        print(f"- {reason}")
    print()
    print("Recommendations:")
    for index, item in enumerate(recommendations, start=1):
        print(f"{index}. [{item.level}] {item.title}")
        print(f"   {item.reason}")
        for command in item.suggested_commands:
            print(f"   command: {command}")
        if item.requires_confirmation:
            print("   confirmation required")


if __name__ == "__main__":
    raise SystemExit(main())
