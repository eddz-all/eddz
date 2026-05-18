from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from projectpilot.git.analyzer import analyze_status
from projectpilot.git.commit_planner import build_commit_plan
from projectpilot.git.executor import get_diff, get_log, run_fetch
from projectpilot.git.inspector import inspect_repository
from projectpilot.git.operation_planner import (
    build_add_plan,
    build_commit_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
)
from projectpilot.git.recommender import build_recommendations
from projectpilot.git.reporter import render_markdown_report, save_markdown_report
from projectpilot.git.safe_executor import run_add, run_commit, run_pull, run_push
from projectpilot.models.commit_plan import CommitPlan, CommitPlanItem
from projectpilot.models.git_status import GitStatus
from projectpilot.models.operation_plan import OperationPlan, OperationResult


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

    commit_plan_command = git_subparsers.add_parser(
        "commit-plan",
        help="Analyze local changes and draft a safe commit plan.",
    )
    add_path_argument(commit_plan_command)
    commit_plan_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    commit_plan_command.set_defaults(handler=handle_git_commit_plan)

    add_plan_command = git_subparsers.add_parser(
        "add-plan",
        help="Plan which files should be staged.",
    )
    add_path_argument(add_plan_command)
    add_plan_command.add_argument(
        "--include",
        nargs="+",
        default=[],
        help="Review-category paths to include in the add plan.",
    )
    add_plan_command.add_argument(
        "--force-include",
        nargs="+",
        default=[],
        help="Exclude-category paths to include anyway.",
    )
    add_plan_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    add_plan_command.set_defaults(handler=handle_git_add_plan)

    add_command = git_subparsers.add_parser(
        "add",
        help="Stage files through a ProjectPilot add plan.",
    )
    add_path_argument(add_command)
    add_command.add_argument(
        "--include",
        nargs="+",
        default=[],
        help="Review-category paths to stage.",
    )
    add_command.add_argument(
        "--force-include",
        nargs="+",
        default=[],
        help="Exclude-category paths to stage anyway.",
    )
    add_command.add_argument("--apply", action="store_true", help="Actually run git add.")
    add_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    add_command.set_defaults(handler=handle_git_add)

    commit_command = git_subparsers.add_parser(
        "commit",
        help="Create a commit from staged files through a ProjectPilot plan.",
    )
    add_path_argument(commit_command)
    commit_command.add_argument("-m", "--message", help="Commit message. Defaults to ProjectPilot's suggestion.")
    commit_command.add_argument("--apply", action="store_true", help="Actually run git commit.")
    commit_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    commit_command.set_defaults(handler=handle_git_commit)

    push_command = git_subparsers.add_parser(
        "push",
        help="Push local commits through a ProjectPilot plan.",
    )
    add_path_argument(push_command)
    push_command.add_argument("--apply", action="store_true", help="Actually run git push.")
    push_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    push_command.set_defaults(handler=handle_git_push)

    pull_command = git_subparsers.add_parser(
        "pull",
        help="Fast-forward pull upstream commits through a ProjectPilot plan.",
    )
    add_path_argument(pull_command)
    pull_command.add_argument("--apply", action="store_true", help="Actually run git pull --ff-only.")
    pull_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    pull_command.set_defaults(handler=handle_git_pull)

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


def handle_git_commit_plan(args: argparse.Namespace) -> int:
    plan = build_commit_plan(Path(args.path))

    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_commit_plan(plan)
    return 0


def handle_git_add_plan(args: argparse.Namespace) -> int:
    plan = build_add_plan(
        Path(args.path),
        include_paths=args.include,
        force_include_paths=args.force_include,
    )

    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_plan(plan)
    return 0


def handle_git_add(args: argparse.Namespace) -> int:
    if not args.apply:
        plan = build_add_plan(
            Path(args.path),
            include_paths=args.include,
            force_include_paths=args.force_include,
        )
        if args.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print_operation_plan(plan)
        print()
        print("Dry run only. Run again with --apply to execute.")
        return 0

    result = run_add(
        Path(args.path),
        include_paths=args.include,
        force_include_paths=args.force_include,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_result(result)
    return 0


def handle_git_commit(args: argparse.Namespace) -> int:
    if not args.apply:
        plan = build_commit_operation_plan(Path(args.path), message=args.message)
        if args.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print_operation_plan(plan)
        print()
        print("Dry run only. Run again with --apply to execute.")
        return 0

    result = run_commit(Path(args.path), message=args.message)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_result(result)
    return 0


def handle_git_push(args: argparse.Namespace) -> int:
    if not args.apply:
        plan = build_push_operation_plan(Path(args.path))
        if args.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print_operation_plan(plan)
        print()
        print("Dry run only. Run again with --apply to execute.")
        return 0

    result = run_push(Path(args.path))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_result(result)
    return 0


def handle_git_pull(args: argparse.Namespace) -> int:
    if not args.apply:
        plan = build_pull_operation_plan(Path(args.path))
        if args.json:
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
            return 0

        print_operation_plan(plan)
        print()
        print("Dry run only. Run again with --apply to execute.")
        return 0

    result = run_pull(Path(args.path))

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_result(result)
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


def print_commit_plan(plan: CommitPlan) -> None:
    print(f"Repository: {plan.repo_path}")
    print(f"Branch: {plan.branch or '(detached HEAD)'}")
    print(plan.summary)
    if plan.suggested_message:
        print(f"Suggested commit message: {plan.suggested_message}")
    print()

    print_plan_group("Suggested include", plan.include)
    print_plan_group("Needs review", plan.review)
    print_plan_group("Suggested exclude", plan.exclude)

    if plan.warnings:
        print("Warnings:")
        for warning in plan.warnings:
            print(f"  - {warning}")
        print()

    print("Suggested commands:")
    for command in plan.suggested_commands:
        print(f"  {command}")


def print_operation_plan(plan: OperationPlan) -> None:
    print(f"Operation: {plan.operation}")
    print(f"Repository: {plan.repo_path}")
    print(f"Risk: {plan.risk}")
    print(f"Allowed: {'yes' if plan.allowed else 'no'}")
    print(f"Requires --apply: {'yes' if plan.requires_apply else 'no'}")
    print(f"Reason: {plan.reason}")
    if plan.suggested_message:
        print(f"Suggested message: {plan.suggested_message}")
    print()
    planned_label = "Planned refs" if plan.operation in {"push", "pull"} else "Planned paths"
    print_file_group(planned_label, plan.planned_paths)
    print_file_group("Review paths", plan.review_paths)
    print_file_group("Excluded paths", plan.excluded_paths)
    if plan.blockers:
        print("Blockers:")
        for blocker in plan.blockers:
            print(f"  - {blocker}")
    if plan.warnings:
        print("Warnings:")
        for warning in plan.warnings:
            print(f"  - {warning}")
    if plan.command:
        print("Command:")
        print("  " + " ".join(plan.command))


def print_operation_result(result: OperationResult) -> None:
    print(f"Operation: {result.operation}")
    print(f"Success: {'yes' if result.success else 'no'}")
    output = (result.stdout + result.stderr).strip()
    if output:
        print(output)
    print()
    print("Updated status:")
    analysis = analyze_status(result.after_status)
    print_status(result.after_status, analysis)


def print_plan_group(title: str, items: list[CommitPlanItem]) -> None:
    print(f"{title}: {len(items)}")
    if not items:
        print("  - None")
        return
    for item in items:
        print(f"  - {item.path} ({item.status})")
        print(f"    {item.reason}")


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
