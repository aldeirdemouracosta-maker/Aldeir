"""Exercise the real agent bridge without requiring a browser engine."""
import asyncio
import threading
import unittest
from pathlib import Path

from support import WorkspaceTemp

from aether.agent import AetherAgent
from aether.config import AetherConfig
from aether.gui.session import AgentSession


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = iter(replies)

    def chat(self, messages, tools=None):
        return next(self.replies)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = WorkspaceTemp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def session(self, replies):
        llm = ScriptedLLM(replies)
        config = AetherConfig(project_root=self.root)
        # Even an enabled project terminal must remain disabled in desktop sessions.
        config.agent.allow_unisolated_terminal = True
        session = AgentSession(config, agent_factory=lambda cfg, **kwargs: AetherAgent(
            cfg, llm=llm, **kwargs
        ))
        self.addCleanup(session.close)
        self.assertTrue(config.agent.allow_unisolated_terminal)
        self.assertFalse(session.config.agent.allow_unisolated_terminal)
        return session

    async def test_real_file_tool_and_plan_arrive_in_ui_queue(self):
        (self.root / "note.txt").write_text("actual tool content", encoding="utf-8")
        session = self.session([
            {"content": "Read note.txt"},
            {"content": "", "tool_calls": [{"function": {
                "name": "read_file", "arguments": {"path": "note.txt"}
            }}]},
            {"content": "Completed"},
        ])
        result = await asyncio.to_thread(session.execute, "inspect", [])
        self.assertEqual(result, "Completed")
        self.assertEqual(session.events.get_nowait(), ("plan", "Read note.txt"))
        kind, (name, output, success) = session.events.get_nowait()
        self.assertEqual((kind, name, success), ("tool", "read_file", True))
        self.assertIn("actual tool content", output)
        self.assertNotIn("run_terminal", session.agent.tools.available_tools)
        self.assertTrue(session.agent.last_evidence.task_id)

    async def test_user_question_does_not_block_event_loop_or_allow_second_task(self):
        session = self.session([
            {"content": "PERGUNTA: Qual arquivo?"},
            {"content": "Read the chosen file"},
            {"content": "Finished"},
        ])
        task = asyncio.create_task(asyncio.to_thread(session.execute, "inspect", []))
        kind, (question, answer) = await asyncio.wait_for(
            asyncio.to_thread(session.events.get), timeout=3
        )
        self.assertEqual((kind, question), ("question", "Qual arquivo?"))
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        with self.assertRaisesRegex(RuntimeError, "execução"):
            session.execute("overlap", [])
        answer.set_result("note.txt")
        self.assertEqual(await asyncio.wait_for(task, 3), "Finished")

    async def test_close_releases_waiting_question_and_rejects_future_runs(self):
        session = self.session([{"content": "PERGUNTA: Continuar?"}])
        task = asyncio.create_task(asyncio.to_thread(session.execute, "inspect", []))
        await asyncio.wait_for(asyncio.to_thread(session.events.get), timeout=3)
        session.close()
        result = await asyncio.wait_for(task, 3)
        self.assertIn("necessária", result)
        self.assertFalse(session.running)
        self.assertIsNone(session.agent)
        with self.assertRaisesRegex(RuntimeError, "encerrada"):
            session.execute("again", [])

    async def test_execution_occurs_in_worker_and_failure_releases_running_state(self):
        session = self.session([])
        main_thread = threading.get_ident()
        observed = []

        def failed_factory(*args, **kwargs):
            observed.append(threading.get_ident())
            raise RuntimeError("backend unavailable")

        session.factory = failed_factory
        with self.assertRaisesRegex(RuntimeError, "backend unavailable"):
            await asyncio.to_thread(session.execute, "inspect", [])
        self.assertNotEqual(observed, [main_thread])
        self.assertFalse(session.running)
