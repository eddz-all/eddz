from __future__ import annotations

import argparse
from getpass import getpass
import json
import sys
from pathlib import Path
from typing import Any

from projectpilot import __version__
from projectpilot.executor.app import run_executor_app
from projectpilot.executor.client import poll_and_run_once, run_connect_loop
from projectpilot.executor.config import build_config, default_config_path, load_config, save_config
from projectpilot.executor.remote import list_ssh_hosts, resolve_ssh_host
from projectpilot.git.analyzer import analyze_status
from projectpilot.git.audit import read_audit_entries
from projectpilot.git.commit_planner import build_commit_plan
from projectpilot.git.doctor import build_doctor_report
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
from projectpilot.models.audit_log import AuditEntry
from projectpilot.models.commit_plan import CommitPlan, CommitPlanItem
from projectpilot.models.doctor import DoctorReport
from projectpilot.models.git_status import GitStatus
from projectpilot.models.operation_plan import OperationPlan, OperationResult


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        print(f"projectpilot {__version__}")
        return 0

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
    parser.add_argument("--version", action="store_true", help="Show ProjectPilot version and exit.")
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

    audit_command = git_subparsers.add_parser(
        "audit",
        help="Show recent ProjectPilot Git operation audit entries.",
    )
    add_path_argument(audit_command)
    audit_command.add_argument("--limit", type=int, default=20, help="Number of audit entries to show, from 1 to 100.")
    audit_command.add_argument(
        "--operation",
        choices=["add", "commit", "push", "pull"],
        help="Filter audit entries by operation.",
    )
    audit_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    audit_command.set_defaults(handler=handle_git_audit)

    doctor_command = git_subparsers.add_parser(
        "doctor",
        help="Check repository Git health and recommend the next step.",
    )
    add_path_argument(doctor_command)
    doctor_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    doctor_command.set_defaults(handler=handle_git_doctor)

    quickstart_command = git_subparsers.add_parser(
        "quickstart",
        help="Show the recommended first commands for a repository.",
    )
    add_path_argument(quickstart_command)
    quickstart_command.set_defaults(handler=handle_git_quickstart)

    executor_parser = subparsers.add_parser("executor", help="Connect this machine to a ProjectPilot backend.")
    executor_subparsers = executor_parser.add_subparsers(dest="executor_command")

    setup_command = executor_subparsers.add_parser(
        "setup",
        help="Save backend connection settings for this machine.",
    )
    add_executor_config_argument(setup_command)
    setup_command.add_argument("--server-url", help="Backend base URL, such as http://127.0.0.1:8000.")
    setup_command.add_argument("--token", help="Executor token. If omitted, ProjectPilot prompts for it.")
    setup_command.add_argument("--executor-id", help="Executor identifier shown in the backend.")
    setup_command.add_argument("--mode", default="local", choices=["local", "central"], help="Executor mode.")
    setup_command.add_argument(
        "--allowed-root",
        help="Root directory this executor is allowed to inspect. Defaults to the current directory.",
    )
    setup_command.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds.")
    setup_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    setup_command.set_defaults(handler=handle_executor_setup)

    status_command = executor_subparsers.add_parser("status", help="Show saved executor connection settings.")
    add_executor_config_argument(status_command)
    status_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    status_command.set_defaults(handler=handle_executor_status)

    connect_command = executor_subparsers.add_parser("connect", help="Poll the backend for read-only detection tasks.")
    add_executor_config_argument(connect_command)
    connect_command.add_argument("--server-url", help="Override backend base URL.")
    connect_command.add_argument("--token", help="Override executor token.")
    connect_command.add_argument("--executor-id", help="Override executor identifier.")
    connect_command.add_argument("--mode", choices=["local", "central"], help="Override executor mode.")
    connect_command.add_argument("--allowed-root", help="Override allowed root directory.")
    connect_command.add_argument("--interval", type=float, help="Override polling interval in seconds.")
    connect_command.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds.")
    connect_command.add_argument("--once", action="store_true", help="Poll and process at most one task.")
    connect_command.add_argument("--json", action="store_true", help="Print machine-readable JSON for --once.")
    connect_command.set_defaults(handler=handle_executor_connect)

    app_command = executor_subparsers.add_parser(
        "app",
        help="Open the local ProjectPilot Executor app.",
        description="Open the local ProjectPilot Executor app.",
    )
    add_executor_config_argument(app_command)
    app_command.add_argument("--host", default="127.0.0.1", help="Local app host.")
    app_command.add_argument("--port", type=int, default=8765, help="Local app port.")
    app_command.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    app_command.set_defaults(handler=handle_executor_app)

    ssh_hosts_command = executor_subparsers.add_parser(
        "ssh-hosts",
        help="List SSH hosts available to this executor.",
    )
    ssh_hosts_command.add_argument(
        "--ssh-config",
        type=Path,
        help="SSH config path. Defaults to ~/.ssh/config.",
    )
    ssh_hosts_command.add_argument("--resolve", action="store_true", help="Resolve each host with ssh -G.")
    ssh_hosts_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    ssh_hosts_command.set_defaults(handler=handle_executor_ssh_hosts)

    return parser


def add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Repository path. Defaults to the current directory.",
    )


def add_executor_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        help="Executor config path. Defaults to ~/.projectpilot/executor.json.",
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


def handle_git_audit(args: argparse.Namespace) -> int:
    entries = read_audit_entries(Path(args.path), limit=args.limit, operation=args.operation)

    if args.json:
        print(json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, indent=2))
        return 0

    print_audit_entries(entries)
    return 0


def handle_git_doctor(args: argparse.Namespace) -> int:
    report = build_doctor_report(Path(args.path))

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_doctor_report(report)
    return 0


def handle_git_quickstart(args: argparse.Namespace) -> int:
    path = Path(args.path)
    print("ProjectPilot Git Quickstart")
    print()
    print("1. Check repository health")
    print(f"   projectpilot git doctor {path}")
    print()
    print("2. Review current changes")
    print(f"   projectpilot git commit-plan {path}")
    print()
    print("3. Stage suggested files")
    print(f"   projectpilot git add {path}")
    print(f"   projectpilot git add {path} --apply")
    print()
    print("4. Commit staged files")
    print(f"   projectpilot git commit {path}")
    print(f"   projectpilot git commit {path} --apply")
    print()
    print("5. Sync safely when upstream exists")
    print(f"   projectpilot git pull {path}")
    print(f"   projectpilot git push {path}")
    print()
    print("6. Review ProjectPilot operation history")
    print(f"   projectpilot git audit {path}")
    return 0


def handle_executor_setup(args: argparse.Namespace) -> int:
    config_path = args.config or default_config_path()
    server_url = args.server_url or input("Backend server URL: ").strip()
    token = args.token or getpass("Executor token: ").strip()
    executor_id = args.executor_id or input("Executor ID [local hostname]: ").strip() or None
    allowed_root = args.allowed_root or input(f"Allowed root [{Path.cwd()}]: ").strip() or str(Path.cwd())

    config = build_config(
        server_url=server_url,
        token=token,
        executor_id=executor_id,
        allowed_root=allowed_root,
        interval=args.interval,
        mode=args.mode,
    )
    saved_path = save_config(config, config_path)

    if args.json:
        print(
            json.dumps(
                {
                    "config_path": str(saved_path),
                    "config": config.to_dict(mask_token=True),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"Executor config saved to: {saved_path}")
    print(f"Server: {config.server_url}")
    print(f"Executor: {config.executor_id}")
    print(f"Mode: {config.mode}")
    print(f"Allowed root: {config.allowed_root}")
    print()
    print("Start polling with:")
    print("  projectpilot executor connect")
    return 0


def handle_executor_status(args: argparse.Namespace) -> int:
    config_path = args.config or default_config_path()
    config = load_config(config_path)
    payload = {
        "config_path": str(config_path.expanduser()),
        "allowed_root_exists": config.allowed_root.exists(),
        "config": config.to_dict(mask_token=True),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("ProjectPilot Executor")
    print()
    print(f"Config: {payload['config_path']}")
    print(f"Server: {config.server_url}")
    print(f"Executor: {config.executor_id}")
    print(f"Mode: {config.mode}")
    print(f"Allowed root: {config.allowed_root}")
    print(f"Allowed root exists: {'yes' if payload['allowed_root_exists'] else 'no'}")
    print(f"Interval: {config.interval}s")
    print(f"Token: {config.to_dict(mask_token=True)['token']}")
    return 0


def handle_executor_connect(args: argparse.Namespace) -> int:
    config = load_or_build_executor_config(args)

    if args.once and args.json:
        result = poll_and_run_once(config, timeout=args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    run_connect_loop(config, once=args.once, timeout=args.timeout)
    return 0


def handle_executor_app(args: argparse.Namespace) -> int:
    run_executor_app(
        host=args.host,
        port=args.port,
        config_path=args.config,
        open_browser=not args.no_browser,
    )
    return 0


def handle_executor_ssh_hosts(args: argparse.Namespace) -> int:
    hosts = list_ssh_hosts(args.ssh_config)
    payload: dict[str, Any] = {"hosts": hosts}
    if args.resolve:
        payload["resolved"] = [resolve_ssh_host(host) for host in hosts]

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not hosts:
        print("No SSH hosts found.")
        return 0
    for host in hosts:
        print(host)
    return 0


def load_or_build_executor_config(args: argparse.Namespace):
    config_path = args.config or default_config_path()
    if config_path.expanduser().exists():
        config = load_config(config_path)
        server_url = args.server_url or config.server_url
        token = args.token or config.token
        executor_id = args.executor_id or config.executor_id
        allowed_root = args.allowed_root or config.allowed_root
        interval = args.interval if args.interval is not None else config.interval
        mode = args.mode or config.mode
    else:
        if not (args.server_url and args.token and args.allowed_root):
            raise RuntimeError("Executor config not found. Run `projectpilot executor setup` first.")
        server_url = args.server_url
        token = args.token
        executor_id = args.executor_id
        allowed_root = args.allowed_root
        interval = args.interval if args.interval is not None else 5.0
        mode = args.mode or "local"

    return build_config(
        server_url=server_url,
        token=token,
        executor_id=executor_id,
        allowed_root=allowed_root,
        interval=interval,
        mode=mode,
    )


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


def print_audit_entries(entries: list[AuditEntry]) -> None:
    if not entries:
        print("No ProjectPilot Git audit entries found.")
        return

    print("Recent Git operations:")
    print()
    for index, entry in enumerate(entries, start=1):
        status = "success" if entry.success else "failed"
        print(f"{index}. {entry.timestamp} {entry.operation} {status}")
        print(f"   branch: {entry.branch or '(detached HEAD)'}")
        print(f"   command: {' '.join(entry.command)}")
        print(f"   before: {short_commit(entry.before_commit)}")
        print(f"   after: {short_commit(entry.after_commit)}")
        print(f"   clean: {format_bool(entry.before_clean)} -> {format_bool(entry.after_clean)}")
        if entry.stdout_summary:
            print(f"   stdout: {entry.stdout_summary.splitlines()[0]}")
        if entry.stderr_summary:
            print(f"   stderr: {entry.stderr_summary.splitlines()[0]}")


def short_commit(commit: str | None) -> str:
    if not commit:
        return "unknown"
    if commit == "(initial)":
        return commit
    return commit[:7]


def format_bool(value: bool) -> str:
    return "yes" if value else "no"


def print_doctor_report(report: DoctorReport) -> None:
    print("Git Doctor")
    print()
    print(f"Health: {report.health}")
    print(f"Risk: {report.risk}")
    print(f"Branch: {report.branch or '(detached HEAD)'}")
    print(f"Upstream: {report.upstream or 'not configured'}")
    print(f"Working tree: {'clean' if report.is_clean else 'dirty'}")
    print(f"Ahead/Behind: +{report.ahead} / -{report.behind}")
    print()
    print("Findings:")
    for finding in report.findings:
        print(f"- {finding}")
    print()
    print("Operation readiness:")
    print(f"- add: {'allowed' if report.can_add else 'blocked'}")
    print(f"- commit: {'allowed' if report.can_commit else 'blocked'}")
    print(f"- push: {'allowed' if report.can_push else 'blocked'}")
    print(f"- pull: {'allowed' if report.can_pull else 'blocked'}")
    print()
    print("Recommended next step:")
    print(f"- {report.recommended_next_step}")


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
