"""Real NiceGUI element tests; optional when desktop dependencies are absent."""
import asyncio
import importlib.util
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from support import WorkspaceTemp

from aether.agent import AetherAgent

HAS_NICEGUI = importlib.util.find_spec("nicegui") is not None
if HAS_NICEGUI:
    from nicegui import Client, ui

    from aether.gui.app import AetherGUI, main


@unittest.skipUnless(HAS_NICEGUI, "NiceGUI optional dependency is not installed")
class GUIRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_count_completion_uses_deterministic_paths_and_releases_controls(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "one.py").write_text("", encoding="utf-8")
        with Client(ui.page("/gui-count-completion")):
            gui = AetherGUI(root)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.session.factory = lambda cfg, **kwargs: AetherAgent(cfg, llm=object(), **kwargs)
            gui.chat.input.set_value("Olá, me diga quantos arquivos Python existem neste projeto")
            await gui.send()
            self.assertEqual(gui.status.text, "Pronto")
            self.assertFalse(gui.reason.visible)
            self.assertFalse(gui.busy)
            self.assertTrue(gui.chat.input.enabled)

    async def test_model_limit_reason_is_visible_with_measured_size(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)

        class LLM:
            def chat(self, *args, **kwargs):
                return {"content": "", "thinking": "x" * 12001}

        with Client(ui.page("/gui-output-limit")):
            gui = AetherGUI(temp.name)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.session.factory = lambda cfg, **kwargs: AetherAgent(cfg, llm=LLM(), **kwargs)
            gui.chat.input.set_value("Explique o projeto")
            await gui.send()
            self.assertEqual(gui.status.text, "Execução incompleta")
            self.assertIn("model_output_limit", gui.reason.text)
            self.assertIn("12001", gui.reason.text)
            self.assertTrue(gui.chat.input.enabled)

    async def test_cancelled_handler_releases_controls_and_next_task_can_complete(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        with Client(ui.page("/gui-cancelled")):
            gui = AetherGUI(temp.name)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.chat.input.set_value("inspect")
            with patch("aether.gui.app.run.io_bound", side_effect=asyncio.CancelledError), \
                    self.assertRaises(asyncio.CancelledError):
                await gui.send()
            self.assertFalse(gui.busy)
            self.assertIn("cancelled", gui.reason.text)
            self.assertTrue(gui.chat.input.enabled)
            gui.chat.input.set_value("Olá, me diga quantos arquivos Python existem neste projeto")
            await gui.send()
            self.assertEqual(gui.status.text, "Pronto")

    async def test_worker_none_return_is_explained_and_controls_released(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        with Client(ui.page("/gui-worker-none")):
            gui = AetherGUI(temp.name)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.chat.input.set_value("inspect")
            with patch("aether.gui.app.run.io_bound", return_value=None):
                await gui.send()
            self.assertIn("worker_no_result", gui.reason.text)
            self.assertFalse(gui.busy)
            self.assertTrue(gui.chat.send_button.enabled)

    async def test_failed_backend_shows_reason_and_releases_all_controls(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        with Client(ui.page("/gui-failure-test")):
            gui = AetherGUI(temp.name)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.chat.input.set_value("inspect")
            with patch.object(gui.session, "execute", side_effect=RuntimeError("backend failed")):
                await gui.send()
            self.assertFalse(gui.busy)
            self.assertIn("backend failed", gui.reason.text)
            for control in (gui.chat.input, gui.chat.send_button,
                            gui.sidebar.skills, gui.sidebar.reset_button):
                self.assertTrue(control.enabled)

    async def test_partial_count_shows_reason_instead_of_only_generic_badge(self):
        import os

        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "one.py").write_text("", encoding="utf-8")
        (root / "private").mkdir()
        scandir = os.scandir

        def blocked(path):
            if Path(path).name == "private":
                raise PermissionError("access denied")
            return scandir(path)

        with Client(ui.page("/gui-partial-test")) as client:
            gui = AetherGUI(root)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.chat.input.set_value("Olá, me diga quantos arquivos Python existem neste projeto")
            with patch("aether.agent.counting.os.scandir", side_effect=blocked):
                await gui.send()
            self.assertEqual(gui.status.text, "Execução incompleta")
            self.assertIn("partial_count", gui.reason.text)
            self.assertTrue(gui.chat.input.enabled)
            texts = [getattr(element, "text", "") for element in client.elements.values()]
            self.assertTrue(any("1 arquivos Python" in text for text in texts))
            self.assertTrue(any("private" in text for text in texts))

    async def test_render_failure_before_worker_still_releases_controls(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        with Client(ui.page("/gui-render-failure-test")):
            gui = AetherGUI(temp.name)
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.chat.input.set_value("inspect")
            with patch.object(gui.chat, "add_message", side_effect=RuntimeError("render failed")):
                await gui.send()
            self.assertFalse(gui.busy)
            self.assertIn("render failed", gui.reason.text)
            self.assertTrue(gui.chat.send_button.enabled)
            self.assertTrue(gui.sidebar.reset_button.enabled)

    async def test_send_from_async_task_with_real_elements_keeps_loop_responsive(self):
        temp = WorkspaceTemp()
        self.addCleanup(temp.cleanup)
        threads = []
        replies = iter([{"content": "Responder à saudação"}, {"content": "Olá!"}])

        class LLM:
            def chat(self, messages, tools=None):
                threads.append(threading.get_ident())
                time.sleep(0.1)
                return next(replies)

        with Client(ui.page("/gui-runtime-test")) as client:
            gui = AetherGUI(Path(temp.name))
            gui.build()
            self.addCleanup(gui.disconnect)
            gui.session.factory = lambda cfg, **kwargs: AetherAgent(cfg, llm=LLM(), **kwargs)
            gui.chat.input.set_value("Olá!")
            # This task has no inherited NiceGUI slot; scroll timers need an explicit parent.
            task = asyncio.create_task(gui.send())
            await asyncio.sleep(0.05)
            self.assertTrue(gui.busy)
            self.assertFalse(task.done())
            self.assertFalse(gui.chat.input.enabled)
            await asyncio.wait_for(task, timeout=3)
            texts = [getattr(element, "text", "") for element in client.elements.values()]
            self.assertIn("Olá!", texts)
            self.assertEqual(gui.status.text, "Pronto")
            self.assertFalse(gui.busy)
            self.assertTrue(gui.chat.input.enabled)
            self.assertTrue(gui.chat.send_button.enabled)
            self.assertTrue(threads)
            self.assertNotIn(threading.get_ident(), threads)
            self.assertFalse(gui.session.config.agent.allow_unisolated_terminal)

    async def test_default_launch_explicitly_selects_native_window(self):
        with patch("sys.argv", ["aether-gui"]), patch("aether.gui.app.ui.run") as run_ui:
            main()
        self.assertTrue(run_ui.call_args.kwargs["native"])
        self.assertEqual(run_ui.call_args.kwargs["window_size"], (1280, 860))
        self.assertEqual(run_ui.call_args.kwargs["host"], "127.0.0.1")

    async def test_explicit_browser_mode_does_not_implicitly_enable_native(self):
        with patch("sys.argv", ["aether-gui", "--browser"]), \
                patch("aether.gui.app.ui.run") as run_ui:
            main()
        self.assertFalse(run_ui.call_args.kwargs["native"])
        self.assertNotIn("window_size", run_ui.call_args.kwargs)
