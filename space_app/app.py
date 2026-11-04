"""Review-only private ZeroGPU application. No work executes at import/startup."""

import hmac
import os
from pathlib import Path

import spaces
import gradio as gr

# Deployment bundle includes backend/zerogpu.py as zerogpu.py (stdlib only).
from zerogpu import GenerationUnavailable, QuotaBudget

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
MODEL_REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
MAX_INPUT_TOKENS = 512
MAX_OUTPUT_TOKENS = 128
_model = None
_tokenizer = None


def _budget():
    path = Path(os.environ.get("SPACE_BUDGET_PATH", ""))
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise GenerationUnavailable()
    return QuotaBudget(
        path, max_attempts=int(os.environ.get("SPACE_MAX_ATTEMPTS", "6"))
    )


def _dispatch_id(request):
    return request.headers.get("x-mm-dispatch-id", "")


def authorize(message, max_new_tokens, request: gr.Request):
    """Gradio CPU validator: all checks and durable reservation precede GPU call."""
    try:
        expected = os.environ.get("ZEROGPU_BACKEND_KEY", "")
        supplied = request.headers.get("x-mm-backend-key", "")
        if (
            os.environ.get("SPACE_EXECUTION_APPROVED") != "true"
            or len(expected) < 32
            or not isinstance(supplied, str)
            or not hmac.compare_digest(expected.encode(), supplied.encode())
            or not isinstance(message, str) or not message.strip()
            or len(message) > 4_000
            or type(max_new_tokens) not in (int, float)
            or max_new_tokens != int(max_new_tokens)
            or not 1 <= max_new_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise GenerationUnavailable()
        _budget().reserve(reservation_id=_dispatch_id(request))
        # Gradio 6 validators must return the validated input values.
        return message, int(max_new_tokens)
    except Exception:
        raise gr.Error("AI generation is disabled or requires operator review.") from None


def _load_qwen():
    """Called only inside an approved GPU job; never during import or validation."""
    global _model, _tokenizer
    if _model is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False, token=False,
        )
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
            token=False, use_safetensors=True, dtype=torch.float16,
        ).to("cuda").eval()
        _model, _tokenizer = model, tokenizer
    return _model, _tokenizer


def _generate_qwen(message, max_new_tokens):
    import torch

    model, tokenizer = _load_qwen()
    text = tokenizer.apply_chat_template(
        [{"role": "user", "content": message}],
        tokenize=False, add_generation_prompt=True,
    )
    # No conversation history; bound tokenized context, never log either text.
    inputs = tokenizer(
        text, return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS,
    ).to("cuda")
    with torch.inference_mode():
        outputs = model.generate(
            **inputs, max_new_tokens=int(max_new_tokens), do_sample=False,
            use_cache=True, pad_token_id=tokenizer.eos_token_id,
        )
    return tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True,
    ).strip()


@spaces.GPU(duration=30, size="large")
def generate(message, max_new_tokens, request: gr.Request):
    """Real Qwen handler; only reachable after the CPU validator reserves a job."""
    try:
        ledger = _budget()
        reservation = _dispatch_id(request)
        ledger.require_active(reservation)
        reply = _generate_qwen(message, int(max_new_tokens))
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 8_000:
            raise GenerationUnavailable()
        ledger.finish(reservation)
        return reply
    except Exception:
        # Do not clear an uncertain reservation or include raw provider/input data.
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
