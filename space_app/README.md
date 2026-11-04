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
| `backend/zerogpu.py` | `zerogpu.py` |

The fourth file reuses the reviewed, stdlib-only durable budget implementation;
do not substitute a different revision from another branch.

## Fail-closed deployment prerequisites — not configured yet

- The backend alone uses a read-scoped `HF_TOKEN` authorized for this private
  Space. Never deploy `HF_WRITE_TOKEN` as a runtime credential.
- A separate random backend key (minimum 32 characters) must be provisioned via
  secure secrets management as `ZEROGPU_BACKEND_KEY` on backend and Space.
  It is sent in an HTTPS header, never as prompt text or Gradio input.
- `SPACE_EXECUTION_APPROVED` is absent/false by default. Only a later approval
  may set it to `true`. A CPU Gradio validator checks this flag, the backend key,
  payload bounds, a dispatch ID, and the Space ledger before GPU scheduling.
- `SPACE_BUDGET_PATH` must point to an existing, trusted, owner-only local SQLite
  ledger, separately manually armed using `QuotaBudget.arm(ManualQuotaSnapshot)`.
  `SPACE_MAX_ATTEMPTS` may lower the six-attempt ceiling, never raise it.
  Missing storage, missing/unarmed ledger, invalid configuration or expired
  evidence rejects execution. Ephemeral storage loss must never auto-arm a ledger.
- The Space and backend each need persistent shared ledgers for their respective
  workers. No automatic reset/replenishment, refund, or uncertain-job recovery.
  A new deployment requires operator review; do not delete/recreate armed ledgers
  to evade exhausted or uncertain state.
- Do not arm or enable either side during code review. No readiness/health-check
  may invoke `/generate`.

Six attempts reserve at most 180 GPU-seconds, with two of the observed eight runs
reserved. These are conservative **application** limits, not HF account quota
readings or billing caps. Other Spaces can consume the same account resources.
No paid fallback, credits, billing calls or account upgrades are implemented.

## Known cold-start limitation

Weights/tokenizer load lazily only inside an approved GPU call. This follows the
user's restriction but differs from HF's recommended module-level loading/CUDA
placement. A first download + load + generation may exceed the hard 30-second
allocation. No live latency or successful inference is claimed. A timeout or
uncertain outcome consumes the local attempt and locks subsequent jobs pending
operator review; do not retry automatically or increase duration without approval.

The fixed model is `Qwen/Qwen2.5-1.5B-Instruct`, revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, safetensors only, remote code disabled.
Input is one message (4,000 characters maximum), tokenized to at most 512 tokens;
output is at most 128 new tokens. User text and credentials are not logged or
stored by application code. Private visibility does not guarantee HF retention.

Official references:
- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://www.gradio.app/docs/gradio/button
- https://huggingface.co/docs/hub/en/spaces-api-endpoints
