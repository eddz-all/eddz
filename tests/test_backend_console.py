from __future__ import annotations

import io
import json
import os
import re
import threading
import time
import unittest
from os import terminal_size
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from projectpilot.cli import main as cli_main
from projectpilot.backend_console import (
    BackendProfile,
    ConsoleUI,
    RICH_AVAILABLE,
    normalize_action_key,
    normalize_nav_key,
    read_action_key,
    render_compact_nav_bar,
    run_backend_console,
)


class BackendConsoleTests(unittest.TestCase):
    def test_default_projectpilot_opens_backend_console_not_executor(self) -> None:
        output = io.StringIO()

        with patch("sys.stdin.isatty", return_value=False), redirect_stdout(output):
            exit_code = cli_main([])

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertIn("ProjectPilot Backend Console", text)
        self.assertNotIn("ProjectPilot Executor connected", text)

    def test_backend_health_cli_reads_backend(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "backend",
                        "--server-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--token",
                        "secret",
                        "--json",
                        "health",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue()), {"status": "ok"})
            self.assertEqual(state["auth"], ["Bearer secret"])
        finally:
            server.shutdown()
            server.server_close()

    def test_backend_detect_cli_posts_project_server_detect(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = cli_main(
                    [
                        "backend",
                        "--server-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--token",
                        "secret",
                        "--json",
                        "detect",
                        "--project-id",
                        "1",
                        "--server-id",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["queued"], True)
            self.assertEqual(state["posts"], ["/projects/1/servers/2/detect"])
            self.assertEqual(state["post_bodies"], [{}])
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_console_opens_on_dashboard(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Dashboard", text)
            self.assertNotIn("Backend Control", text)
            self.assertNotIn("Actions", text)
            self.assertNotIn("Action [", text)
            if RICH_AVAILABLE:
                self.assertIn("Bindings", text)
                self.assertIn("AI Ops", text)
                self.assertIn("API Map", text)
                self.assertIn("Settings", text)
            else:
                self.assertIn("D/P/S/B/A/T/M/G", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_footer_renders_as_tui_status_line_not_panel(self) -> None:
        output = io.StringIO()
        ui = ConsoleUI(output, rich_enabled=True)
        ui.width = 80

        ui.render_footer()

        text = output.getvalue()
        self.assertIn("Pages", text)
        self.assertIn("Enter Refresh", text)
        self.assertIn("R Detect", text)
        self.assertIn("D/P/S", text)
        self.assertIn("q Quit", text)
        self.assertNotIn("\u250c", text)
        self.assertNotIn("\u2502", text)
        self.assertNotIn("\u2514", text)

    def test_narrow_footer_does_not_clip_half_shortcuts(self) -> None:
        output = io.StringIO()
        ui = ConsoleUI(output, rich_enabled=True)
        ui.width = 70

        ui.render_footer()

        text = output.getvalue()
        self.assertIn("q Quit", text)
        self.assertNotIn("~", text)

    def test_rich_console_uses_actual_narrow_terminal_width(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal width assertions.")
        output = io.StringIO()

        with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((70, 24))):
            ui = ConsoleUI(output, rich_enabled=True)

        self.assertEqual(ui.width, 70)

    def test_rich_console_uses_actual_short_terminal_height(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal height assertions.")
        output = io.StringIO()

        with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((45, 8))):
            ui = ConsoleUI(output, rich_enabled=True)

        self.assertEqual(ui.width, 45)
        self.assertEqual(ui.height, 8)

    def test_rich_console_uses_full_wide_terminal_width(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal width assertions.")
        output = io.StringIO()

        with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((220, 40))):
            ui = ConsoleUI(output, rich_enabled=True)

        self.assertEqual(ui.width, 220)
        self.assertEqual(ui.height, 40)

    def test_rich_frame_refreshes_terminal_size_between_frames(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal frame assertions.")
        output = io.StringIO()
        sizes = [terminal_size((80, 5)), terminal_size((140, 8))]

        with patch("projectpilot.backend_console.shutil.get_terminal_size", side_effect=sizes):
            ui = ConsoleUI(output, rich_enabled=True)
            ui.begin_frame()
            ui.console.print("small")
            ui.end_frame()

        self.assertEqual(ui.width, 140)
        self.assertEqual(ui.height, 8)
        text = output.getvalue()
        self.assertIn("\x1b[8;1H", text)
        self.assertNotIn("\x1b[9;1H", text)

    def test_rich_frame_clears_screen_after_resize(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal frame assertions.")
        output = io.StringIO()
        sizes = [
            terminal_size((80, 5)),
            terminal_size((80, 5)),
            terminal_size((120, 7)),
        ]

        with patch("projectpilot.backend_console.shutil.get_terminal_size", side_effect=sizes):
            ui = ConsoleUI(output, rich_enabled=True)
            ui.begin_frame()
            ui.console.print("first")
            ui.end_frame()
            ui.begin_frame()
            ui.console.print("second")
            ui.end_frame()

        text = output.getvalue()
        self.assertIn("\x1b[2J\x1b[H", text)
        self.assertIn("\x1b[7;1H", text)

    def test_compact_nav_keeps_all_shortcut_markers_on_narrow_width(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for compact navigation assertions.")

        panel = render_compact_nav_bar(selected="8", width=70)
        text = panel.renderable.plain

        for marker in ("1", "2", "3", "4", "5", "6", "7", "8"):
            self.assertIn(marker, text)

    def test_rich_frame_clear_moves_to_home_instead_of_appending(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal frame assertions.")
        output = io.StringIO()
        ui = ConsoleUI(output, rich_enabled=True)

        ui.clear()

        self.assertEqual(output.getvalue(), "\x1b[2J\x1b[H")

    def test_rich_frame_writer_crops_without_terminal_scroll(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal frame assertions.")
        output = io.StringIO()

        with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((80, 5))):
            ui = ConsoleUI(output, rich_enabled=True)
            ui.begin_frame()
            for index in range(8):
                ui.console.print(f"line {index}")
            ui.end_frame()

        text = output.getvalue()
        plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
        self.assertIn("\x1b[1;1H", text)
        self.assertIn("\x1b[5;1H", text)
        self.assertNotIn("\x1b[6;1H", text)
        self.assertIn("line 4", plain)
        self.assertNotIn("line 5", plain)
        self.assertNotIn("\n", text)

    def test_rich_frame_writer_preserves_footer_when_content_is_tall(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for terminal frame assertions.")
        output = io.StringIO()

        with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((80, 5))):
            ui = ConsoleUI(output, rich_enabled=True)
            ui.begin_frame()
            for index in range(8):
                ui.console.print(f"line {index}")
            ui.render_footer()
            ui.end_frame()

        text = output.getvalue()
        plain = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
        self.assertIn("\x1b[5;1H", text)
        self.assertIn("line 0", plain)
        self.assertIn("line 3", plain)
        self.assertNotIn("line 4", plain)
        self.assertNotIn("line 7", plain)
        self.assertIn("q Quit", plain)
        self.assertNotIn("\n", text)

    def test_keyboard_shortcuts_normalize_to_navigation(self) -> None:
        self.assertEqual(normalize_action_key("\t"), "down")
        self.assertEqual(normalize_action_key("\x0e"), "down")
        self.assertEqual(normalize_action_key("\x10"), "up")
        self.assertEqual(normalize_action_key("\x1b[Z"), "up")
        self.assertEqual(normalize_action_key("h"), "h")
        self.assertEqual(normalize_action_key("j"), "j")
        self.assertEqual(normalize_action_key("k"), "k")
        self.assertEqual(normalize_nav_key("P"), "2")
        self.assertEqual(normalize_nav_key("S"), "3")
        self.assertEqual(normalize_nav_key("G"), "8")
        self.assertEqual(normalize_nav_key("H"), "")
        self.assertEqual(normalize_nav_key("Q"), "0")
        self.assertEqual(normalize_nav_key("x"), "")

    def test_compact_dashboard_omits_long_gui_sections(self) -> None:
        if not RICH_AVAILABLE:
            self.skipTest("Rich is required for compact dashboard layout assertions.")
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((100, 30))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("Overview", text)
            self.assertNotIn("AI Recommendation", text)
            self.assertNotIn("Git & Environment Matrix", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_dashboard_survives_backend_offline(self) -> None:
        output = io.StringIO()
        choices = iter(["0"])

        result = run_backend_console(
            BackendProfile(
                server_url="http://127.0.0.1:1",
                token="secret",
                timeout=1,
            ),
            output=output,
            input_fn=lambda _: next(choices),
            interactive=True,
        )

        self.assertTrue(result["success"])
        text = output.getvalue()
        self.assertIn("ProjectPilot | Dashboard", text)
        self.assertTrue("Backend      offline" in text or "Backend error" in text)
        self.assertIn("Backend Error", text)

    def test_interactive_projects_page_uses_app_shell(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["2", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            self.assertNotIn("Action [", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_arrow_enter_opens_selected_page(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["down", "enter", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            if RICH_AVAILABLE:
                self.assertIn(">2  Projects", text)
                self.assertNotIn("Dashboard     *", text)
            self.assertNotIn("Unknown shortcut", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_arrow_switches_pages_immediately(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["down", "down", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            self.assertIn("ProjectPilot | Servers", text)
            self.assertNotIn("Unknown shortcut", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_arrow_navigation_does_not_refetch_dashboard(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["down", "down", "up", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            self.assertEqual(state["gets"].count("/health"), 1)
            self.assertEqual(state["gets"].count("/projects"), 2)
            self.assertEqual(state["gets"].count("/servers"), 2)
            self.assertEqual(state["gets"].count("/executor/tasks"), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_unknown_key_is_ignored(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["x", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertNotIn("Unknown shortcut", text)
            self.assertEqual(state["gets"].count("/health"), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_quit_shortcuts_exit_without_rendering_quit_page(self) -> None:
        for quit_key in ("q", "0"):
            with self.subTest(quit_key=quit_key):
                server, _ = start_backend_test_server()
                try:
                    output = io.StringIO()
                    choices = iter([quit_key])

                    result = run_backend_console(
                        BackendProfile(
                            server_url=f"http://127.0.0.1:{server.server_port}",
                            token="secret",
                        ),
                        output=output,
                        input_fn=lambda _: next(choices),
                        interactive=True,
                    )

                    self.assertTrue(result["success"])
                    self.assertNotIn("ProjectPilot | Quit", output.getvalue())
                finally:
                    server.shutdown()
                    server.server_close()

    def test_interactive_tab_enter_opens_selected_page(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["\t", "enter", "0"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            self.assertNotIn("Unknown shortcut", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_mnemonic_shortcuts_open_pages(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["p", "s", "g", "q"])

            with patch("projectpilot.backend_console.shutil.get_terminal_size", return_value=terminal_size((140, 35))):
                result = run_backend_console(
                    BackendProfile(
                        server_url=f"http://127.0.0.1:{server.server_port}",
                        token="secret",
                    ),
                    output=output,
                    input_fn=lambda _: next(choices),
                    interactive=True,
                )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            self.assertIn("ProjectPilot | Servers", text)
            self.assertIn("ProjectPilot | Settings", text)
            self.assertNotIn("Unknown shortcut", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_projects_page_ignores_enter_after_shortcut(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["2\n", "\n", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertEqual(text.count("ProjectPilot | Projects"), 1)
            self.assertNotIn("Unknown shortcut", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_console_ignores_escape_sequence_debris(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["\x1b[A", "[", "B", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Dashboard", text)
            self.assertNotIn("Unknown shortcut", text)
            self.assertNotIn("ProjectPilot | Projects", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_read_action_key_collects_delayed_arrow_sequence(self) -> None:
        try:
            import pty
            import tty
        except ImportError:
            self.skipTest("pty module is required for terminal input assertions.")

        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        stdin = os.fdopen(slave_fd, "r", buffering=1)

        def write_split_arrow() -> None:
            os.write(master_fd, b"\x1b")
            time.sleep(0.04)
            os.write(master_fd, b"[B")

        writer = threading.Thread(target=write_split_arrow, daemon=True)
        try:
            writer.start()
            with patch("sys.stdin", stdin):
                self.assertEqual(read_action_key(), "down")
        finally:
            writer.join(timeout=1)
            stdin.close()
            os.close(master_fd)

    def test_read_action_key_keeps_rapid_arrow_sequences_separate(self) -> None:
        try:
            import pty
            import tty
        except ImportError:
            self.skipTest("pty module is required for terminal input assertions.")

        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        stdin = os.fdopen(slave_fd, "r", buffering=1)

        try:
            os.write(master_fd, b"\x1b[B\x1b[B")
            with patch("sys.stdin", stdin):
                self.assertEqual(read_action_key(), "down")
                self.assertEqual(read_action_key(), "down")
        finally:
            stdin.close()
            os.close(master_fd)

    def test_read_action_key_reads_long_home_and_end_sequences(self) -> None:
        try:
            import pty
            import tty
        except ImportError:
            self.skipTest("pty module is required for terminal input assertions.")

        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        stdin = os.fdopen(slave_fd, "r", buffering=1)

        try:
            os.write(master_fd, b"\x1b[1~\x1b[4~")
            with patch("sys.stdin", stdin):
                self.assertEqual(read_action_key(), "home")
                self.assertEqual(read_action_key(), "end")
        finally:
            stdin.close()
            os.close(master_fd)

    def test_read_action_key_does_not_swallow_key_after_plain_escape(self) -> None:
        try:
            import pty
            import tty
        except ImportError:
            self.skipTest("pty module is required for terminal input assertions.")

        master_fd, slave_fd = pty.openpty()
        tty.setraw(slave_fd)
        stdin = os.fdopen(slave_fd, "r", buffering=1)

        try:
            os.write(master_fd, b"\x1bq")
            with patch("sys.stdin", stdin):
                self.assertEqual(read_action_key(), "esc")
                self.assertEqual(read_action_key(), "0")
        finally:
            stdin.close()
            os.close(master_fd)

    def test_interactive_arrow_enter_detect_posts_once(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["r", "down", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Run Detection", text)
            self.assertEqual(state["posts"], ["/projects/1/servers/2/detect"])
            self.assertEqual(state["post_bodies"], [{}])
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_projects_page_renders_unexpected_json_payload(self) -> None:
        server, _ = start_backend_test_server(projects_payload={"error": "unexpected shape"})
        try:
            output = io.StringIO()
            choices = iter(["2", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Projects", text)
            self.assertIn("unexpected shape", text)
            self.assertNotIn("Error:", text)
            self.assertNotIn("Action [", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_table_pages_tolerate_non_object_rows(self) -> None:
        server, _ = start_backend_test_server(
            projects_payload=["bad-project"],
            servers_payload=["bad-server"],
            tasks_payload=["bad-task"],
        )
        try:
            output = io.StringIO()
            choices = iter(["2", "3", "6", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("bad-project", text)
            self.assertIn("bad-server", text)
            self.assertIn("bad-task", text)
            self.assertNotIn("Error:", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_projects_page_keeps_backend_error_in_shell(self) -> None:
        output = io.StringIO()
        choices = iter(["2", "0"])

        result = run_backend_console(
            BackendProfile(
                server_url="http://127.0.0.1:1",
                token="secret",
                timeout=1,
            ),
            output=output,
            input_fn=lambda _: next(choices),
            interactive=True,
        )

        self.assertTrue(result["success"])
        text = output.getvalue()
        self.assertIn("ProjectPilot | Projects", text)
        self.assertIn("Backend Error", text)
        self.assertNotIn("Unknown choice", text)

    def test_interactive_detect_page_posts_empty_json_body_and_uses_app_shell(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["r", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Run Detection", text)
            self.assertNotIn("Action [", text)
            self.assertEqual(state["posts"], ["/projects/1/servers/2/detect"])
            self.assertEqual(state["post_bodies"], [{}])
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_detect_page_ignores_enter_after_shortcut(self) -> None:
        server, state = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["r\n", "\n", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            self.assertEqual(state["posts"], ["/projects/1/servers/2/detect"])
            self.assertEqual(state["post_bodies"], [{}])
        finally:
            server.shutdown()
            server.server_close()

    def test_interactive_gui_shortcut_pages_do_not_error(self) -> None:
        server, _ = start_backend_test_server()
        try:
            output = io.StringIO()
            choices = iter(["b", "a", "m", "g", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | Bindings", text)
            self.assertIn("ProjectPilot | AI Ops", text)
            self.assertIn("ProjectPilot | API Map", text)
            self.assertIn("ProjectPilot | Settings", text)
            if RICH_AVAILABLE:
                self.assertIn("Project Server Bindings", text)
                self.assertIn("AI Settings", text)
                self.assertIn("Frontend API Contract", text)
                self.assertIn("Backend Connection", text)
            else:
                self.assertIn("/demo/projectpilot", text)
                self.assertIn("openai", text)
                self.assertIn("/projects", text)
                self.assertIn("server_url", text)
            self.assertNotIn("Backend Error", text)
            self.assertNotIn("Backend error", text)
            self.assertNotIn("Unknown choice", text)
        finally:
            server.shutdown()
            server.server_close()

    def test_backend_html_error_is_summarized_in_shell(self) -> None:
        server, _ = start_backend_test_server(
            ai_settings_error_body="""
            <!DOCTYPE html>
            <html>
              <head><title>Cloudflare Tunnel error | viewers.example | Cloudflare</title></head>
              <body>
                <h1>Error code 1033</h1>
                <script>window.alert("long noisy page")</script>
                <div id="cf-wrapper">very long html body</div>
              </body>
            </html>
            """,
            ai_settings_error_status=530,
        )
        try:
            output = io.StringIO()
            choices = iter(["a", "0"])

            result = run_backend_console(
                BackendProfile(
                    server_url=f"http://127.0.0.1:{server.server_port}",
                    token="secret",
                ),
                output=output,
                input_fn=lambda _: next(choices),
                interactive=True,
            )

            self.assertTrue(result["success"])
            text = output.getvalue()
            self.assertIn("ProjectPilot | AI Ops", text)
            self.assertIn("HTTP 530", text)
            self.assertIn("Cloudflare Tunnel error", text)
            self.assertNotIn("<!DOCTYPE html>", text)
            self.assertNotIn("<script>", text)
            self.assertNotIn("cf-wrapper", text)
        finally:
            server.shutdown()
            server.server_close()


def start_backend_test_server(
    *,
    projects_payload: Any | None = None,
    servers_payload: Any | None = None,
    tasks_payload: Any | None = None,
    bindings_payload: Any | None = None,
    ai_settings_payload: Any | None = None,
    ai_settings_error_body: str | None = None,
    ai_settings_error_status: int = 530,
    status_payload: Any | None = None,
    activities_payload: Any | None = None,
) -> tuple[ThreadingHTTPServer, dict[str, Any]]:
    state: dict[str, Any] = {
        "auth": [],
        "gets": [],
        "posts": [],
        "post_bodies": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            state["auth"].append(self.headers.get("Authorization"))
            state["gets"].append(self.path)
            if self.path == "/health":
                self.write_json({"status": "ok"})
                return
            if self.path == "/projects":
                self.write_json(
                    projects_payload
                    if projects_payload is not None
                    else [{"id": 1, "name": "ProjectPilot", "path": "/demo/projectpilot"}]
                )
                return
            if self.path == "/servers":
                self.write_json(
                    servers_payload
                    if servers_payload is not None
                    else [{"id": 2, "name": "server-b", "connection_mode": "executor"}]
                )
                return
            if self.path == "/executor/tasks":
                self.write_json(tasks_payload if tasks_payload is not None else [])
                return
            if self.path == "/projects/1/servers":
                self.write_json(
                    bindings_payload
                    if bindings_payload is not None
                    else [
                        {
                            "binding_id": 10,
                            "project_id": 1,
                            "server_id": 2,
                            "server_name": "server-b",
                            "host": "127.0.0.1",
                            "port": 8000,
                            "username": "eddz",
                            "connection_mode": "executor",
                            "project_path": "/demo/projectpilot",
                            "created_at": "2026-06-03T10:00:00",
                        }
                    ]
                )
                return
            if self.path == "/ai/settings":
                if ai_settings_error_body is not None:
                    self.write_raw(ai_settings_error_body, status=ai_settings_error_status)
                    return
                self.write_json(
                    ai_settings_payload
                    if ai_settings_payload is not None
                    else {
                        "provider": "openai",
                        "model": "gpt-5",
                        "api_key_configured": True,
                        "status": "ok",
                    }
                )
                return
            if self.path == "/projects/1/status":
                self.write_json(
                    status_payload
                    if status_payload is not None
                    else {"project": {"id": 1, "name": "ProjectPilot"}, "servers": []}
                )
                return
            if self.path.startswith("/operation-logs"):
                self.write_json(activities_payload if activities_payload is not None else [])
                return
            self.send_error(404)

        def do_POST(self) -> None:
            state["auth"].append(self.headers.get("Authorization"))
            state["posts"].append(self.path)
            state["post_bodies"].append(read_json_body(self))
            if self.path == "/projects/1/servers/2/detect":
                self.write_json({"queued": True})
                return
            self.send_error(404)

        def write_json(self, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def write_raw(self, payload: str, *, status: int) -> None:
            body = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


def read_json_body(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
