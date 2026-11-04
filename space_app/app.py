"""Private ZeroGPU chat app. Nothing executes by default.

Two SEPARATE default-disabled approval flags:
  SPACE_MODEL_INIT_APPROVED=true  -> load Qwen at Space startup (module level, via
                                     the documented ZeroGPU CUDA emulation)
  SPACE_EXECUTION_APPROVED=true   -> accept and run signed inference requests
The Space keeps no quota state. The backend's local ledger is the only counter; the
Space only checks that each request carries a fresh tag signed with the shared key.
"""

import os
import time

import spaces
import gradio as gr

# Deployment bundle includes backend/dispatch_auth.py as dispatch_auth.py (stdlib).
from dispatch_auth import (
    ID_HEADER, TAG_HEADER, TIME_HEADER, AuthError, verify_dispatch,
)

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
MAX_INPUT_TOKENS = 512
MAX_OUTPUT_TOKENS = 128
_model = None
_tokenizer = None


def _load_components():
    """Startup-only. Under ZeroGPU, .to('cuda') at module level is emulated and
    allocates no GPU time. Never called by the validator or the GPU handler."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False, token=False,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
        token=False, use_safetensors=True, dtype=torch.float16,
    ).to("cuda").eval()
    return model, tokenizer


def initialize_model():
    """Gated, no warm-up generation, no retry. Failure leaves the Space refusing."""
    global _model, _tokenizer
    if os.environ.get("SPACE_MODEL_INIT_APPROVED") != "true" or _model is not None:
        return False
    try:
        _model, _tokenizer = _load_components()
    except Exception:
        _model = _tokenizer = None  # fail closed; no error text is retained
        return False
    return True


initialize_model()


def _verify(message, max_new_tokens, request):
    """Local-only check: fresh dispatch signed with the shared key (no network)."""
    key = os.environ.get("ZEROGPU_BACKEND_KEY", "")
    headers = request.headers
    try:
        issued_at = int(headers.get(TIME_HEADER.lower(), ""))
    except (TypeError, ValueError):
        raise AuthError() from None
    if len(key) < 32 or not verify_dispatch(
        key, headers.get(ID_HEADER.lower(), ""), issued_at, int(max_new_tokens),
        message, headers.get(TAG_HEADER.lower(), ""), time.time(),
    ):
        raise AuthError()


def authorize(message, max_new_tokens, request: gr.Request):
    """Gradio CPU validator: every check precedes GPU scheduling."""
    try:
        if (
            os.environ.get("SPACE_EXECUTION_APPROVED") != "true"
            or not isinstance(message, str) or not message.strip()
            or len(message) > 4_000
            or type(max_new_tokens) not in (int, float)
            or max_new_tokens != int(max_new_tokens)
            or not 1 <= max_new_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise AuthError()
        _verify(message, max_new_tokens, request)
        # Gradio 6 validators must return the validated input values.
        return message, int(max_new_tokens)
    except Exception:
        raise gr.Error("AI generation is disabled or requires operator review.") from None


def _generate_qwen(message, max_new_tokens):
    """Inference only. The model must already have been loaded at startup."""
    import torch

    if _model is None or _tokenizer is None:
        raise AuthError()
    text = _tokenizer.apply_chat_template(
        [{"role": "user", "content": message}],
        tokenize=False, add_generation_prompt=True,
    )
    # No conversation history; bound tokenized context, never log either text.
    inputs = _tokenizer(
        text, return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS,
    ).to("cuda")
    with torch.inference_mode():
        outputs = _model.generate(
            **inputs, max_new_tokens=int(max_new_tokens), do_sample=False,
            use_cache=True, pad_token_id=_tokenizer.eos_token_id,
        )
    return _tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True,
    ).strip()


@spaces.GPU(duration=30, size="large")
def generate(message, max_new_tokens, request: gr.Request):
    """Real handler, bounded to 30 s. No model loading, warm-up or retry here.
    Re-verifies the signed dispatch locally as defense in depth."""
    try:
        if os.environ.get("SPACE_EXECUTION_APPROVED") != "true":
            raise AuthError()
        _verify(message, max_new_tokens, request)
        reply = _generate_qwen(message, int(max_new_tokens))
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 8_000:
            raise AuthError()
        return reply
    except Exception:
        # No raw provider/input data; the backend keeps the attempt spent.
        raise gr.Error("AI generation is unavailable; operator review is required.") from None


with gr.Blocks(
    title="Mind Machine - inference disabled", analytics_enabled=False,
) as demo:
    gr.Markdown(
        "# Mind Machine\n\nInference is disabled pending separate execution approval."
    )
    message_input = gr.Textbox(visible=False)
    token_limit = gr.Number(value=128, precision=0, visible=False)
    result = gr.Textbox(visible=False)
    trigger = gr.Button(visible=False, interactive=False)
    trigger.click(
        fn=generate, inputs=[message_input, token_limit], outputs=result,
        validator=authorize, api_name="generate", api_visibility="undocumented",
        concurrency_limit=1, concurrency_id="account-gpu",
    )

if __name__ == "__main__":
    demo.queue(api_open=False, default_concurrency_limit=1, max_size=1).launch(
        share=False, show_error=False,
    )
