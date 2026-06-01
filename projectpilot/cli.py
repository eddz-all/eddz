from __future__ import annotations

import argparse
from getpass import getpass
import json
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from projectpilot import __version__
from projectpilot.executor.app import run_executor_app
from projectpilot.executor.backend import (
    ExecutorBackendStore,
    create_executor_backend_server,
    default_backend_storage_path,
    run_executor_backend,
)
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
    build_cherry_pick_operation_plan,
    build_commit_operation_plan,
    build_high_risk_operation_plan,
    build_merge_operation_plan,
    build_pull_operation_plan,
    build_push_operation_plan,
    build_revert_operation_plan,
    build_stash_operation_plan,
    build_switch_operation_plan,
    build_tag_operation_plan,
)
from projectpilot.git.recommender import build_recommendations
from projectpilot.git.reporter import render_markdown_report, save_markdown_report
from projectpilot.git.safe_executor import (
    run_add,
    run_cherry_pick,
    run_commit,
    run_merge,
    run_pull,
    run_push,
    run_revert,
    run_stash,
    run_switch,
    run_tag,
)
from projectpilot.git.state_map import build_state_map
from projectpilot.git.sync_planner import build_sync_plan
from projectpilot.integration.smart_git import analyze_repository
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

    switch_command = git_subparsers.add_parser(
        "switch",
        help="Switch branches through a ProjectPilot plan.",
    )
    switch_command.add_argument("target", help="Local branch to switch to, or new branch name with --create.")
    switch_command.add_argument("path", nargs="?", default=".", help="Repository path. Defaults to the current directory.")
    switch_command.add_argument("--create", action="store_true", help="Create the branch before switching.")
    switch_command.add_argument("--start-point", help="Start point for --create.")
    switch_command.add_argument("--apply", action="store_true", help="Actually run git switch.")
    switch_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    switch_command.set_defaults(handler=handle_git_switch)

    merge_command = git_subparsers.add_parser(
        "merge",
        help="Plan or run a safe fast-forward merge.",
    )
    merge_command.add_argument("source", help="Branch or ref to merge into the current branch.")
    merge_command.add_argument("path", nargs="?", default=".", help="Repository path. Defaults to the current directory.")
    merge_command.add_argument("--apply", action="store_true", help="Actually run git merge --ff-only.")
    merge_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    merge_command.set_defaults(handler=handle_git_merge)

    stash_command = git_subparsers.add_parser(
        "stash",
        help="Stash local changes through a ProjectPilot plan.",
    )
    add_path_argument(stash_command)
    stash_command.add_argument("-m", "--message", help="Stash message. Defaults to a ProjectPilot message.")
    stash_command.add_argument(
        "--include-untracked",
        action="store_true",
        help="Also stash untracked files.",
    )
    stash_command.add_argument("--apply", action="store_true", help="Actually run git stash push.")
    stash_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    stash_command.set_defaults(handler=handle_git_stash)

    tag_command = git_subparsers.add_parser(
        "tag",
        help="Create a Git tag through a ProjectPilot plan.",
    )
    tag_command.add_argument("name", help="Tag name to create.")
    tag_command.add_argument("path", nargs="?", default=".", help="Repository path. Defaults to the current directory.")
    tag_command.add_argument("-m", "--message", help="Create an annotated tag with this message.")
    tag_command.add_argument("--apply", action="store_true", help="Actually run git tag.")
    tag_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    tag_command.set_defaults(handler=handle_git_tag)

    revert_command = git_subparsers.add_parser(
        "revert",
        help="Revert a commit through a ProjectPilot plan.",
    )
    revert_command.add_argument("revision", help="Commit to revert.")
    revert_command.add_argument("path", nargs="?", default=".", help="Repository path. Defaults to the current directory.")
    revert_command.add_argument("--commit", action="store_true", help="Create the revert commit immediately.")
    revert_command.add_argument("--apply", action="store_true", help="Actually run git revert.")
    revert_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    revert_command.set_defaults(handler=handle_git_revert)

    cherry_pick_command = git_subparsers.add_parser(
        "cherry-pick",
        help="Cherry-pick a commit through a ProjectPilot plan.",
    )
    cherry_pick_command.add_argument("revision", help="Commit to cherry-pick.")
    cherry_pick_command.add_argument("path", nargs="?", default=".", help="Repository path. Defaults to the current directory.")
    cherry_pick_command.add_argument("--commit", action="store_true", help="Create the cherry-pick commit immediately.")
    cherry_pick_command.add_argument("--apply", action="store_true", help="Actually run git cherry-pick.")
    cherry_pick_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    cherry_pick_command.set_defaults(handler=handle_git_cherry_pick)

    danger_command = git_subparsers.add_parser(
        "danger-plan",
        help="Explain why a high-risk Git operation is blocked by ProjectPilot.",
    )
    danger_command.add_argument(
        "operation",
        choices=["reset-hard", "clean", "force-push", "rebase"],
        help="High-risk operation to explain.",
    )
    add_path_argument(danger_command)
    danger_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    danger_command.set_defaults(handler=handle_git_danger_plan)

    audit_command = git_subparsers.add_parser(
        "audit",
        help="Show recent ProjectPilot Git operation audit entries.",
    )
    add_path_argument(audit_command)
    audit_command.add_argument("--limit", type=int, default=20, help="Number of audit entries to show, from 1 to 100.")
    audit_command.add_argument(
        "--operation",
        choices=["add", "commit", "push", "pull", "switch", "merge", "stash", "tag", "revert", "cherry-pick"],
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

    map_command = git_subparsers.add_parser(
        "map",
        help="Show the Git state map across working tree, staged files, local commits, and remote.",
    )
    add_path_argument(map_command)
    map_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    map_command.set_defaults(handler=handle_git_map)

    sync_plan_command = git_subparsers.add_parser(
        "sync-plan",
        help="Explain safe push/pull decisions for the current branch.",
    )
    add_path_argument(sync_plan_command)
    sync_plan_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    sync_plan_command.set_defaults(handler=handle_git_sync_plan)

    analyze_command = git_subparsers.add_parser(
        "analyze",
        help="Run a bundled smart Git analysis for backend and Agent integration.",
    )
    add_path_argument(analyze_command)
    analyze_command.add_argument(
        "--include",
        nargs="+",
        default=[],
        help="Analyses to include: status, doctor, map, sync-plan, commit-plan.",
    )
    analyze_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    analyze_command.set_defaults(handler=handle_git_analyze)

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

    connect_command = executor_subparsers.add_parser("connect", help="Poll the backend for detection and approved tasks.")
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

    backend_command = executor_subparsers.add_parser(
        "backend",
        help="Run a minimal local Executor backend for MVP integration.",
    )
    backend_command.add_argument("--host", default="127.0.0.1", help="Backend host.")
    backend_command.add_argument("--port", type=int, default=8780, help="Backend port.")
    backend_command.add_argument(
        "--storage",
        type=Path,
        default=default_backend_storage_path(),
        help="JSON storage path for tasks, snapshots, and operation logs.",
    )
    backend_command.add_argument("--token", required=True, help="Bearer token accepted from executors.")
    backend_command.set_defaults(handler=handle_executor_backend)

    enqueue_command = executor_subparsers.add_parser(
        "enqueue",
        help="Create a task in the local Executor backend JSON queue.",
    )
    enqueue_command.add_argument(
        "--storage",
        type=Path,
        default=default_backend_storage_path(),
        help="JSON storage path used by `projectpilot executor backend`.",
    )
    enqueue_command.add_argument("--payload-json", help="Full task payload as a JSON object.")
    enqueue_command.add_argument("--type", help="Task type, for example detect_environment.")
    enqueue_command.add_argument("--executor-id", help="Optional executor assignment.")
    enqueue_command.add_argument("--project-path", help="Local or remote project path.")
    enqueue_command.add_argument("--ssh-host", help="SSH Host alias for remote tasks.")
    enqueue_command.add_argument("--operation", help="Git operation for approved execution tasks.")
    enqueue_command.add_argument("--approved", action="store_true", help="Mark execution task as approved.")
    enqueue_command.add_argument("--expected-command", nargs="+", help="Approved command array.")
    enqueue_command.add_argument("--params-json", help="Task params as a JSON object.")
    enqueue_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    enqueue_command.set_defaults(handler=handle_executor_enqueue)

    run_local_command = executor_subparsers.add_parser(
        "run-local",
        help="Run an embedded backend and executor in one process for local demos.",
    )
    run_local_command.add_argument("--host", default="127.0.0.1", help="Embedded backend host.")
    run_local_command.add_argument("--port", type=int, default=0, help="Embedded backend port. Defaults to any free port.")
    run_local_command.add_argument("--token", default="dev-token", help="Bearer token used by the embedded executor.")
    run_local_command.add_argument(
        "--storage",
        type=Path,
        help="Persist embedded backend JSON storage. Defaults to a temporary file.",
    )
    run_local_command.add_argument("--executor-id", default="projectpilot-local-agent", help="Local executor id.")
    run_local_command.add_argument(
        "--allowed-root",
        default=".",
        help="Root directory this embedded executor may inspect or modify.",
    )
    run_local_command.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds.")
    run_local_command.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds.")
    run_local_command.add_argument("--once", action="store_true", help="Process one task and exit.")
    run_local_command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    run_local_command.add_argument("--no-task", action="store_true", help="Start without queuing an initial task.")
    run_local_command.add_argument("--payload-json", help="Full task payload as a JSON object.")
    run_local_command.add_argument("--type", default="smart_git_analyze", help="Task type to enqueue.")
    run_local_command.add_argument("--project-path", default=".", help="Project path for the default task.")
    run_local_command.add_argument(
        "--analyses",
        nargs="+",
        default=["map", "sync-plan", "commit-plan"],
        help="Smart Git analyses for the default task.",
    )
    run_local_command.add_argument("--ssh-host", help="SSH Host alias for remote tasks.")
    run_local_command.add_argument("--operation", help="Git operation for approved execution tasks.")
    run_local_command.add_argument("--approved", action="store_true", help="Mark execution task as approved.")
    run_local_command.add_argument("--expected-command", nargs="+", help="Approved command array.")
    run_local_command.add_argument("--params-json", help="Task params as a JSON object.")
    run_local_command.set_defaults(handler=handle_executor_run_local)

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


def handle_git_switch(args: argparse.Namespace) -> int:
    plan = build_switch_operation_plan(
        Path(args.path),
        target=args.target,
        create=args.create,
        start_point=args.start_point,
    )
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_switch(
        Path(args.path),
        target=args.target,
        create=args.create,
        start_point=args.start_point,
    )
    return print_applied_operation(result, args.json)


def handle_git_merge(args: argparse.Namespace) -> int:
    plan = build_merge_operation_plan(Path(args.path), source=args.source)
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_merge(Path(args.path), source=args.source)
    return print_applied_operation(result, args.json)


def handle_git_stash(args: argparse.Namespace) -> int:
    plan = build_stash_operation_plan(
        Path(args.path),
        message=args.message,
        include_untracked=args.include_untracked,
    )
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_stash(
        Path(args.path),
        message=args.message,
        include_untracked=args.include_untracked,
    )
    return print_applied_operation(result, args.json)


def handle_git_tag(args: argparse.Namespace) -> int:
    plan = build_tag_operation_plan(Path(args.path), name=args.name, message=args.message)
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_tag(Path(args.path), name=args.name, message=args.message)
    return print_applied_operation(result, args.json)


def handle_git_revert(args: argparse.Namespace) -> int:
    plan = build_revert_operation_plan(Path(args.path), revision=args.revision, commit=args.commit)
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_revert(Path(args.path), revision=args.revision, commit=args.commit)
    return print_applied_operation(result, args.json)


def handle_git_cherry_pick(args: argparse.Namespace) -> int:
    plan = build_cherry_pick_operation_plan(Path(args.path), revision=args.revision, commit=args.commit)
    if not args.apply:
        return print_dry_run_operation(plan, args.json)

    result = run_cherry_pick(Path(args.path), revision=args.revision, commit=args.commit)
    return print_applied_operation(result, args.json)


def handle_git_danger_plan(args: argparse.Namespace) -> int:
    command_map = {
        "reset-hard": (["git", "reset", "--hard"], "Reset the working tree and index to another commit."),
        "clean": (["git", "clean", "-fd"], "Delete untracked files and directories."),
        "force-push": (["git", "push", "--force"], "Rewrite the remote branch history."),
        "rebase": (["git", "rebase"], "Rewrite local commit history."),
    }
    command, reason = command_map[args.operation]
    plan = build_high_risk_operation_plan(Path(args.path), args.operation, reason, command)

    if args.json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_plan(plan)
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


def handle_git_map(args: argparse.Namespace) -> int:
    state_map = build_state_map(Path(args.path))

    if args.json:
        print(json.dumps(state_map.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_state_map(state_map.to_dict())
    return 0


def handle_git_sync_plan(args: argparse.Namespace) -> int:
    sync_plan = build_sync_plan(Path(args.path))

    if args.json:
        print(json.dumps(sync_plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_sync_plan(sync_plan.to_dict())
    return 0


def handle_git_analyze(args: argparse.Namespace) -> int:
    analysis = analyze_repository(Path(args.path), analyses=args.include or None)

    if args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
        return 0 if analysis.get("success") else 1

    print_smart_git_analysis(analysis)
    return 0 if analysis.get("success") else 1


def print_dry_run_operation(plan: OperationPlan, as_json: bool) -> int:
    if as_json:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_plan(plan)
    print()
    print("Dry run only. Run again with --apply to execute.")
    return 0


def print_applied_operation(result: OperationResult, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print_operation_result(result)
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
    print("6. Work with branches and release markers")
    print(f"   projectpilot git switch feature/demo {path} --create")
    print(f"   projectpilot git merge feature/demo {path}")
    print(f"   projectpilot git tag v1.0.0 {path}")
    print()
    print("7. Review ProjectPilot operation history")
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


def handle_executor_backend(args: argparse.Namespace) -> int:
    run_executor_backend(
        host=args.host,
        port=args.port,
        token=args.token,
        storage_path=args.storage,
    )
    return 0


def handle_executor_enqueue(args: argparse.Namespace) -> int:
    task = build_executor_task_payload(args)
    created = ExecutorBackendStore(args.storage).create_task(task)

    if args.json:
        print(json.dumps({"success": True, "task": created}, ensure_ascii=False, indent=2))
        return 0

    print(f"Task queued: {created['id']}")
    print(f"Type: {created['type']}")
    print(f"Storage: {args.storage.expanduser()}")
    return 0


def handle_executor_run_local(args: argparse.Namespace) -> int:
    if args.storage:
        return run_embedded_executor_stack(args, args.storage)

    with tempfile.TemporaryDirectory() as temp_dir:
        return run_embedded_executor_stack(args, Path(temp_dir) / "executor-backend.json")


def run_embedded_executor_stack(args: argparse.Namespace, storage: Path) -> int:
    server = create_executor_backend_server(
        host=args.host,
        port=args.port,
        token=args.token,
        storage_path=storage,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_host, actual_port = server.server_address[:2]
    backend_url = f"http://{actual_host}:{actual_port}"
    queued_task: dict[str, Any] | None = None

    try:
        if not args.no_task:
            task = build_executor_task_payload(args)
            queued_task = ExecutorBackendStore(storage).create_task(task)

        config = build_config(
            server_url=backend_url,
            token=args.token,
            executor_id=args.executor_id,
            allowed_root=args.allowed_root,
            interval=args.interval,
            mode="local",
        )

        if args.once or args.json:
            result = poll_and_run_once(config, timeout=args.timeout)
            state = ExecutorBackendStore(storage).snapshot()
            payload = {
                "success": True,
                "backend_url": backend_url,
                "storage": str(storage.expanduser()),
                "queued_task": queued_task,
                "executor_result": result,
                "state": state,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            print_embedded_executor_result(payload)
            return 0

        print(f"ProjectPilot local stack: {backend_url}")
        print(f"Storage: {storage.expanduser()}")
        if queued_task:
            print(f"Queued task: {queued_task['id']} ({queued_task['type']})")
        print("Press Ctrl+C to stop.")
        print()
        run_connect_loop(config, once=False, timeout=args.timeout)
        return 0
    finally:
        server.shutdown()
        server.server_close()


def print_embedded_executor_result(payload: dict[str, Any]) -> None:
    queued_task = payload.get("queued_task") or {}
    executor_result = payload.get("executor_result") or {}
    task_result = executor_result.get("result") if isinstance(executor_result, dict) else None
    task_success = isinstance(task_result, dict) and bool(task_result.get("success"))

    print("ProjectPilot local stack completed.")
    print(f"Backend: {payload.get('backend_url')}")
    print(f"Storage: {payload.get('storage')}")
    if queued_task:
        print(f"Task: {queued_task.get('id')} ({queued_task.get('type')})")
    print(f"Submitted: {'yes' if executor_result.get('submitted') else 'no'}")
    if executor_result.get("submitted"):
        print(f"Result: {'success' if task_success else 'failed'}")


def build_executor_task_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_json:
        payload = json.loads(args.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("--payload-json must be a JSON object.")
        return payload

    if not args.type:
        raise ValueError("--type is required when --payload-json is not provided.")

    payload: dict[str, Any] = {"type": args.type}
    if args.executor_id:
        payload["executor_id"] = args.executor_id
    if args.project_path:
        payload["project_path"] = args.project_path
    if payload["type"] == "smart_git_analyze" and getattr(args, "analyses", None):
        payload["analyses"] = args.analyses
    if args.ssh_host:
        payload["ssh_host"] = args.ssh_host
    if args.operation:
        payload["operation"] = args.operation
    if args.approved:
        payload["approved"] = True
    if args.expected_command:
        payload["expected_command"] = args.expected_command
    if args.params_json:
        params = json.loads(args.params_json)
        if not isinstance(params, dict):
            raise ValueError("--params-json must be a JSON object.")
        payload["params"] = params
    return payload


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
    planned_label = "Planned refs" if plan.operation in {"push", "pull"} else "Planned targets"
    if plan.operation in {"add", "commit", "merge", "stash"}:
        planned_label = "Planned paths"
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
    if plan.rollback_commands:
        print("Rollback:")
        for command in plan.rollback_commands:
            print("  " + " ".join(command))


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


def print_state_map(report: dict[str, Any]) -> None:
    print(f"Repository: {report['repo_path']}")
    print(f"Branch: {report['branch'] or '(detached HEAD)'}")
    print(f"Upstream: {report['upstream'] or 'not configured'}")
    print(f"State: {report['state']}")
    print(f"Risk: {report['risk']}")
    print()
    print_state_map_group("Working Tree", report["working_tree"])
    print_state_map_group("Staged", report["staged"])
    print_state_map_group("Untracked", report["untracked"])
    print_state_map_group("Conflicted", report["conflicted"])
    print()
    local_commits = report.get("local_commits") or {}
    remote = report.get("remote") or {}
    print("Local Commits")
    print(f"  ahead: {local_commits.get('ahead', 0)}")
    for commit in local_commits.get("commits", []):
        print(f"  - {commit}")
    if not local_commits.get("commits"):
        print("  - None")
    print()
    print("Remote")
    print(f"  upstream: {remote.get('upstream') or 'not configured'}")
    print(f"  behind: {remote.get('behind', 0)}")
    print(f"  diverged: {format_bool(bool(remote.get('diverged')))}")
    print()
    print("Next Steps:")
    for step in report["next_steps"]:
        print(f"- {step}")


def print_state_map_group(title: str, items: list[dict[str, Any]]) -> None:
    print(f"{title}: {len(items)}")
    if not items:
        print("  - None")
        return
    for item in items:
        print(f"  - {item['status']} {item['path']}")


def print_sync_plan(report: dict[str, Any]) -> None:
    print("Git Sync Plan")
    print()
    print(f"Repository: {report['repo_path']}")
    print(f"Branch: {report['branch'] or '(detached HEAD)'}")
    print(f"Upstream: {report['upstream'] or 'not configured'}")
    print(f"Risk: {report['risk']}")
    print(f"Sync state: {report['sync_state']}")
    print(f"Working tree: {report['working_tree_state']}")
    print(f"Ahead/Behind: +{report['ahead']} / -{report['behind']}")
    print(f"Can push: {format_bool(report['can_push'])}")
    print(f"Can fast-forward pull: {format_bool(report['can_pull_ff_only'])}")
    print()
    print("Decision:")
    print(f"- {report['recommended_action']}")
    print(report["explanation"])
    print()
    if report["operation_plans"]:
        print("Allowed operation plans:")
        for plan in report["operation_plans"]:
            print(f"- {plan['operation']}: {' '.join(plan.get('command', []))}")
    if report["blocked_operations"]:
        print("Blocked operations:")
        for operation in report["blocked_operations"]:
            print(f"- {operation['operation']}: {operation['reason']}")
    print()
    print("Next Steps:")
    for step in report["next_steps"]:
        print(f"- {step}")


def print_smart_git_analysis(analysis: dict[str, Any]) -> None:
    if not analysis.get("success"):
        print(f"Smart Git analysis failed: {analysis.get('message', 'unknown error')}", file=sys.stderr)
        return
    print("Smart Git Analysis")
    print()
    print(f"Repository: {analysis['repo_path']}")
    print(f"Branch: {analysis.get('branch') or '(detached HEAD)'}")
    print(f"Upstream: {analysis.get('upstream') or 'not configured'}")
    print(f"State: {analysis.get('state')}")
    print(f"Risk: {analysis.get('risk')}")
    print()
    reports = analysis.get("reports", {})
    if "map" in reports:
        print_state_map(reports["map"])
        print()
    if "sync_plan" in reports:
        print_sync_plan(reports["sync_plan"])
        print()
    if analysis.get("next_steps"):
        print("Combined Next Steps:")
        for step in analysis["next_steps"]:
            print(f"- {step}")


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
