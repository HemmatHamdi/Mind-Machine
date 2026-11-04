---
title: Mind Machine Chat
sdk: gradio
sdk_version: 6.31.0
python_version: 3.12.12
app_file: app.py
---

# Review-only Qwen ZeroGPU application

**Do not upload or run this bundle before separate deployment approval.**
Keep the existing Space private, default ZeroGPU; do not change hardware/billing.

The genuine Qwen handler is registered directly with Gradio and decorated with
`spaces.GPU(duration=30, size="large")`. Startup registers code only. There is no
model initialization, download, inference, example cache, timer, warmup, load
event, or automatic GPU invocation at startup. The only visible UI is status.

Future bundle manifest (not uploaded by this PR):

| Repository source | Space destination |
| --- | --- |
| `space_app/app.py` | `app.py` |
| `space_app/requirements.txt` | `requirements.txt` |
| `space_app/README.md` | `README.md` |
| `backend/dispatch_auth.py` | `dispatch_auth.py` |

The fourth file is stdlib-only (HMAC dispatch verification and one admission POST).
The Space bundle contains **no** database, ledger or quota code and holds **no**
database credentials. Do not substitute a revision from another branch.

## Request flow (offline-tested with fakes; platform behaviour unverified)

1. Backend authenticates the user and applies the per-user limit.
2. Backend signs a dispatch (ID, time, token limit, message) with `ZEROGPU_BACKEND_KEY`
   and **reserves** it in the central ledger (charges one attempt, takes the single
   job lock). Nothing is sent before the reservation commits.
3. Backend submits once to the private Space with only the ID/time/tag headers.
   The root key is never sent.
4. The Space CPU validator verifies the tag locally, then POSTs a purpose-bound
   proof to the backend control endpoint (`ZEROGPU_CONTROL_URL`, HTTPS). The ledger
   admits each reservation exactly once, before the ticket expires.
5. The `@spaces.GPU(duration=30, size="large")` handler re-verifies the tag locally
   and runs bounded inference on the already-loaded model.
6. Backend marks the reservation complete only after a valid reply. Errors,
   timeouts and cancellation never refund and keep the job lock (quarantine).

## Approval flags (all default off)

- `SPACE_MODEL_INIT_APPROVED=true` loads Qwen at Space startup (module level, ZeroGPU
  CUDA emulation). No warm-up generation, no retry, never inside the GPU handler.
- `SPACE_EXECUTION_APPROVED=true` accepts and runs admitted requests. It is independent
  of the init flag; a failed or absent load makes the handler refuse.
- `ZEROGPU_BACKEND_KEY` (min 32 chars) and `ZEROGPU_CONTROL_URL` (https only).
- Backend only: read-scope `HF_TOKEN`; ledger via `LIBSQL_URL`/`LIBSQL_AUTH_TOKEN`
  (none provisioned). Never use `HF_WRITE_TOKEN` at runtime.
- Backend deployment: one worker/replica, HTTPS at the trusted ingress, no automatic
  POST retries. Storage that is unavailable, corrupt, missing or incompatible
  rejects every request; there is no auto-create, reset, snapshot restore or refund.

Six attempts reserve at most 180 GPU-seconds, with two of the observed eight runs
reserved. These are conservative **application** limits, not HF account quota
readings or billing caps. No paid fallback or billing calls are implemented.

## Remaining limitations

Startup loading follows HF's documented approach, but a 30-second allocation is not
proven sufficient and no live latency, successful inference, Turso transaction
behaviour or ZeroGPU emulation behaviour is claimed. The control endpoint must be
reachable by the Space over HTTPS.

The fixed model is `Qwen/Qwen2.5-1.5B-Instruct`, revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, safetensors only, remote code disabled.
Input is one message (4,000 characters maximum), tokenized to at most 512 tokens;
output is at most 128 new tokens. User text and credentials are not logged or
stored by application code. Private visibility does not guarantee HF retention.

Official references:
- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://www.gradio.app/docs/gradio/button
- https://huggingface.co/docs/hub/en/spaces-api-endpoints
