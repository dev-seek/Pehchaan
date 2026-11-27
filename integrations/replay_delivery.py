"""Run the platform tool wrapper against a local API without speech credentials."""

import asyncio
import os

from pehchaan_sdk import LiveClient

from .call_gate import CallGate


async def main() -> None:
    async with LiveClient(os.getenv("PEHCHAAN_URL", "http://127.0.0.1:8000"), os.environ["PEHCHAAN_V2_TOKEN"]) as client:
        gate = CallGate(client, step="callback")
        writes = []

        async def write(arguments, key):
            writes.append((arguments, key))

        async def propose(phone, attempt):
            result = await gate.execute(
                "update_callback", {"order_id": "PK-7823", "callback_phone": phone},
                operation_id=attempt, write=write,
            )
            print(f"{attempt}: {result.outcome} ({result.reason})")
            return result.outcome

        try:
            await gate.finalized("Order ID PK-7823; callback number 9000012345")
            assert await propose("9000012345", "initial-proposal") == "ask"
            print(gate.question.prompt)
            gate.question_played(gate.question.id)
            await gate.finalized("9000012346")
            assert await propose("9000012345", "old-number") == "review"
            assert await propose("9000012346", "new-number") == "allow"
            assert len(writes) == 1 and writes[0][0]["callback_phone"] == "9000012346"
            print("Recorded one simulated tool write, using the caller's readback.")
        finally:
            await gate.close()


if __name__ == "__main__":
    asyncio.run(main())
