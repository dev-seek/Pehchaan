"""LiveKit reference agent with a protected delivery callback tool."""

from __future__ import annotations

import asyncio
import os

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, cli, function_tool
from livekit.agents.llm import ChatContext, ChatMessage

from pehchaan_live.contracts import Provider
from pehchaan_sdk import LiveClient

from .call_gate import CallGate


class DeliveryAgent(Agent):
    def __init__(self, gate: CallGate, provider: Provider):
        super().__init__(
            instructions=(
                "You handle delivery callback updates. Ask the caller to state their order ID and callback number. "
                "When both are available, call update_callback with the literal values. A callback write is successful "
                "only if the tool reports allow. The platform speaks its clarification, so do not repeat it. "
                "If the tool reports review, tell the caller the update was deferred and continue the conversation."
            )
        )
        self.gate = gate
        self.provider = provider
        self.writes: dict[str, dict[str, str]] = {}
        self._spoken_id = None
        self._playout_tasks: set[asyncio.Task] = set()

    def _ask(self) -> None:
        question = self.gate.question
        if not question or question.id == self._spoken_id:
            return
        self._spoken_id = question.id
        handle = self.session.say(question.prompt, allow_interruptions=True)

        async def track():
            await handle.wait_for_playout()
            if not handle.interrupted:
                self.gate.question_played(question.id)

        task = asyncio.create_task(track())
        self._playout_tasks.add(task)
        task.add_done_callback(self._playout_tasks.discard)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        await self.gate.finalized(new_message.text_content or "", provider=self.provider)
        self._ask()

    @function_tool
    async def update_callback(self, context: RunContext, order_id: str, callback_phone: str) -> str:
        """Update a callback number using the exact finalized caller values."""

        async def write(arguments: dict[str, str], key: str) -> None:
            self.writes.setdefault(key, arguments)

        result = await self.gate.execute(
            "update_callback",
            {"order_id": order_id, "callback_phone": callback_phone},
            operation_id="callback-update",
            write=write,
        )
        self._ask()
        return result.outcome


server = AgentServer()


@server.rtc_session()
async def delivery(ctx: JobContext) -> None:
    client = LiveClient(os.getenv("PEHCHAAN_URL", "http://127.0.0.1:8000"), os.environ["PEHCHAAN_V2_TOKEN"])
    gate = CallGate(client, step="callback")

    async def cleanup() -> None:
        await gate.close()
        await client.close()

    ctx.add_shutdown_callback(cleanup)
    stt = os.environ["LIVEKIT_STT"]
    provider_name, _, model = stt.partition("/")
    agent = DeliveryAgent(gate, Provider(name=provider_name, model=model))
    session = AgentSession(stt=stt, llm=os.environ["LIVEKIT_LLM"], tts=os.environ["LIVEKIT_TTS"])

    @session.on("user_state_changed")
    def on_user_state_changed(event):
        if event.new_state == "speaking":
            gate.block()

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
