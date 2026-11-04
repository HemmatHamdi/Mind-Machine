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

Bundle manifest (nothing is uploaded by this PR):

| Repository source | Space destination |
| --- | --- |
| `space_app/app.py` | `app.py` |
| `space_app/requirements.txt` | `requirements.txt` |
| `space_app/README.md` | `README.md` |
| `backend/dispatch_auth.py` | `dispatch_auth.py` |

`dispatch_auth.py` is stdlib-only. The Space has **no** database or quota code; the
backend's local ledger is the only counter.

## Flags and secrets (all default off)

- `SPACE_MODEL_INIT_APPROVED=true`: load Qwen once at Space startup (module level,
  documented ZeroGPU CUDA emulation). No warm-up generation, no retry, never inside
  the GPU handler. A failed load leaves the Space refusing requests.
- `SPACE_EXECUTION_APPROVED=true`: accept signed requests. Independent of the flag
  above.
- `ZEROGPU_BACKEND_KEY` (32+ chars) as a Space secret, the same value as the backend.
- The backend alone uses a read-scope `HF_TOKEN`. Never deploy `HF_WRITE_TOKEN`.

The validator and the `@spaces.GPU(duration=30, size="large")` handler each verify the
signed tag locally (ID, time, token limit and message; valid for 90 seconds). There
is no replay store on the Space: a captured tag could be reused within 90 seconds
by someone holding the private-Space token. The backend ledger still caps total use.

## Limitations (unverified)

Startup loading follows HF's documented approach, but no live cold-start time,
ZeroGPU emulation behaviour or successful inference is claimed. A 30-second GPU slot
is not proven sufficient. Six attempts reserve at most 180 GPU-seconds with two of
eight runs held back; these are application limits, not HF billing caps.

The fixed model is `Qwen/Qwen2.5-1.5B-Instruct`, revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, safetensors only, remote code disabled.
Input is one message (4,000 characters maximum, 512 tokens); output at most 128 new
tokens. User text and credentials are not logged or stored by application code.

Official references:
- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://www.gradio.app/docs/gradio/button
- https://huggingface.co/docs/hub/en/spaces-api-endpoints
