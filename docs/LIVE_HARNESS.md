# Pehchaan live action checks

An existing voice agent can check a proposed callback, collection amount or appointment before writing it to a customer
system. Send finalized caller turns, declare the action fields and rules, then check the arguments at the tool boundary.
The decision can allow the proposal, ask one question or send the write for review.

## Run the correction demo

Use two terminals from the repository root. The example token is for local loopback only.

```bash
make setup
export PEHCHAAN_V2_TOKEN=local-loopback-check-2026-strong
make demo
```

```bash
export PEHCHAAN_V2_TOKEN=local-loopback-check-2026-strong
.venv/bin/python -m integrations.replay_delivery
```

The transcript gives a callback ending in **45**. Pehchaan asks the caller to repeat it, and the reply ends in **46**.
The original tool proposal goes to review. The corrected proposal passes and the reference writer records one simulated
write. [HTTP contract](API.md#v2-live-action-checks)

## Install the Python client

```bash
python -m pip install .
```

```python
from pehchaan_live.contracts import Action, Turn
from pehchaan_sdk import LiveClient

async with LiveClient(base_url, gateway_token) as client:
    turn = await client.turn(Turn(
        call_id=call_id, turn_id=turn_id, sequence=1,
        transcript="Order ID PK-7823; callback number 9000012345", step="callback",
    ))
    # Speak turn.question.prompt if returned, then submit the finalized answer.
    decision = await client.check(Action(
        call_id=call_id, turn_id=current_turn_id, idempotency_key=check_id,
        action="update_callback", arguments=proposed_arguments,
    ))
    if decision.outcome == "allow":
        await write_once(proposed_arguments, operation_id)
```

The gateway defines the current turn, question playback state, tool proposal and operation ID. The complete wrapper
handles interruptions, expired checks, transport failures and concurrent writes. [Reference wrapper](../integrations/call_gate.py)

## Use the LiveKit reference agent

Install the optional integration and run the agent in a configured LiveKit project.

```bash
.venv/bin/python -m pip install '.[livekit]'
export PEHCHAAN_URL=http://127.0.0.1:8000
export PEHCHAAN_V2_TOKEN=local-loopback-check-2026-strong
export LIVEKIT_STT='your-provider/your-stt-model'
export LIVEKIT_LLM='your-provider/your-llm-model'
export LIVEKIT_TTS='your-provider/your-tts-model:your-voice'
.venv/bin/python -m integrations.livekit_delivery dev
```

Use the project's `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`. Choose models enabled in the project.
Say “order ID PK-7823” and “callback number 9000012345” in the same caller turn with a pause, then repeat the full
number during the clarification. The finalized-turn hook ingests caller speech before the agent responds. The tool
method checks the proposal before its in-memory write. Playback completion determines whether the next turn can
answer the question. [LiveKit pipeline hooks](https://docs.livekit.io/agents/logic/nodes/)

## Adapt a versioned policy

The delivery policy declares callback, PIN and collection amount actions. The appointment policy declares booking and
rescheduling actions. Both use the same runtime. [Delivery](../data/policies/delivery.yaml) · [Appointment](../data/policies/appointment.yaml)

- Give each field cues, a type, a question, an evidence rule, normalization and fallback. Order the `required` action
  fields by question priority. Declared `optional` fields are checked when present. Use `steps` to scope actions.
- A positive candidate starts a complete clause with a declared cue. The examples use sentences, semicolons, line breaks, or a conjunction
  followed by another declared cue. The policies list phrases that defer conditional and cancelled statements. Dates use ISO
  format, and times use 24-hour HH:MM.
- Types cover literal text, identifiers, Indian mobile or E.164 phones, Indian postal codes, exact decimals with currency,
  dates, times and enums. Policy can opt into case folding, spoken digits for Indian codes and formatted INR amounts.
  Tool arguments are strings. An unrecognized validator or constraint goes to review.
- Choose `transcript`, `agreement` or `readback` per field. The delivery policy asks for a caller readback for phone,
  PIN and amount. The appointment policy asks for the date. Caller readback can support a later proposal.

For staging, set `PEHCHAAN_V2_TENANTS` to a YAML file. Each row chooses a fixed policy or reviewed rollout pointer.
Paths are relative to that file. Tokens are loaded from the named environment variables and must be distinct, with at
least 24 characters. Gateway credentials submit turns and check writes. Reviewer credentials attest to outcomes.

```yaml
- id: example-platform
  token_env: EXAMPLE_GATEWAY_TOKEN
  review_token_env: EXAMPLE_REVIEWER_TOKEN
  policy: ./data/policies/delivery.yaml
```

The reference server keeps bounded in-memory state in one process. The gateway deletes it at hangup and the server
expires it after ten minutes. Use call-affine routing or shared atomic state before scaling to multiple instances.
Active calls without fresh state after a restart require review. Optional INFO events under `pehchaan.live.audit`
record decision IDs, outcomes, versions and timing with transcript and argument contents omitted.

[Benchmark protocol](LIVE_BENCHMARK.md) · [Pilot and rollout brief](LIVE_PILOT.md)
