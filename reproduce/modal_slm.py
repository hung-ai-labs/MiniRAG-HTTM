"""Serve the paper's SLM on a rented GPU, speaking the OpenAI protocol.

Why this exists: the local Ollama path works but pins the laptop's GPU for
about three hours per run. This is the same model on a rented A10G, reachable
over HTTP, so the machine stays cool and a run takes under an hour.

Why vLLM rather than transformers: minirag/llm/hf.py generates one prompt at a
time (hf.py:150), which is what made the local estimate 10-14 hours before
Ollama. vLLM batches concurrent requests, and it speaks the OpenAI-compatible
protocol that minirag/llm/gemini.py already uses -- so pointing GEMINI_API_BASE
at this URL runs the whole pipeline with no new backend code.

    modal deploy reproduce/modal_slm.py       # one-off, no GPU billed yet
    modal app stop minirag-slm                # when finished

Which model is served comes from a serving file read at deploy time (SLM_SERVING,
default the Qwen file). A second SLM gets its own app, so both URLs can live:

    SLM_SERVING=reproduce/research/serving_minicpm_modal.json modal deploy reproduce/modal_slm.py
    modal app stop minirag-slm-minicpm

The GPU spins up on the first request and shuts down after SCALEDOWN seconds
of silence, so an idle deployment costs nothing.
"""

import json
import os
from pathlib import Path

import modal

QWEN_SERVING = Path(__file__).resolve().parent / "research" / "serving_qwen_modal.json"
DEFAULT_GPU = "A10G"                  # 24 GB: fits the 3B in bf16 with room for KV cache
PORT = 8000
SCALEDOWN = 300                       # idle seconds before the GPU is released

# Context has to clear the real prompt sizes: measured on this project's index,
# the retrieved context is 3,908 tokens at the median and 8,291 at the maximum,
# before the Entities table and the prompt template are added.
# Qwen2.5-3B hỗ trợ 32k; để dư sau sự cố tràn 16.413 token (max_model_len trong file serving).


def load_serving(path=None):
    """The serving file names the model; inside the container the deploy-time copy is used."""
    if path is None and os.environ.get("MINIRAG_SERVING_JSON"):
        return json.loads(os.environ["MINIRAG_SERVING_JSON"])
    path = Path(path or os.environ.get("SLM_SERVING") or QWEN_SERVING)
    return json.loads(path.read_text(encoding="utf-8"))


def vllm_command(serving, api_key):
    """vllm serve arguments. Qwen's file has no revision or override, so its command is the one used since 10/09;
    Phi's has no tokenizer/code revision or remote code, so its command is the one of 03/11. Only the static-RoPE
    Phi file (07/11) has served_alias and hf_overrides."""
    model = serving["model"]
    names = [model, "minirag-slm"] + ([serving["served_alias"]] if serving.get("served_alias") else [])
    args = ["vllm serve", model,
            "--served-model-name", *names,
            "--host 0.0.0.0", f"--port {PORT}",
            f"--max-model-len {serving['max_model_len']}"]
    if serving.get("serve_revision"):
        args.append(f"--revision {serving['model_revision']}")
        # MiniCPM3's config is repository code: pin it and the tokenizer to the same commit as the weights.
        for key, flag in (("tokenizer_revision", "--tokenizer-revision"), ("code_revision", "--code-revision")):
            if serving.get(key):
                args.append(f"{flag} {serving[key]}")
    if serving.get("trust_remote_code"):
        args.append("--trust-remote-code")
    if serving.get("override_generation_config"):
        # Single-quoted for the shell; the JSON itself has no quote characters to escape.
        args.append(f"--override-generation-config '{json.dumps(serving['override_generation_config'])}'")
    if serving.get("hf_overrides"):
        # Phi-3.5 static RoPE (serving_phi_rope_modal.json): replaces config keys before the model is built.
        args.append(f"--hf-overrides '{json.dumps(serving['hf_overrides'])}'")
    args += ["--api-key", api_key, "--disable-log-requests"]
    return " ".join(args)


SERVING = load_serving()
APP_NAME = SERVING.get("modal_app", "minirag-slm")
# MiniCPM3 keeps full K/V per head in vLLM 0.11 (~0.91 MiB a token): a 32k window does not fit an A10G.
GPU = SERVING.get("gpu", DEFAULT_GPU)
app = modal.App(APP_NAME)
# Only what vllm_command reads goes into the image: the container cannot read the local file, and free text
# (provenance notes) can hold quotes that break the image's ENV line.
SERVE_KEYS = ("model", "model_revision", "serve_revision", "tokenizer_revision", "code_revision",
              "trust_remote_code", "max_model_len", "override_generation_config", "served_alias", "hf_overrides")

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.11.0", "huggingface_hub[hf_transfer]==0.35.3")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1",
          "MINIRAG_SERVING_JSON": json.dumps({k: SERVING[k] for k in SERVE_KEYS if k in SERVING})})
)

# Weights persist between runs, so only the first cold start pays the download.
hf_cache = modal.Volume.from_name("minirag-hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("minirag-vllm-cache", create_if_missing=True)

# The endpoint is public, so it needs a token of its own. Create it once with:
#   modal secret create minirag-slm-key MINIRAG_SLM_KEY=<pick-something-long>
auth = modal.Secret.from_name("minirag-slm-key")


@app.function(
    image=vllm_image,
    gpu=GPU,
    scaledown_window=SCALEDOWN,
    timeout=30 * 60,
    volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
    secrets=[auth],
    max_containers=1,
)
@modal.concurrent(max_inputs=32)      # vLLM batches these; this is the whole speed win
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve():
    import subprocess

    subprocess.Popen(vllm_command(load_serving(), os.environ["MINIRAG_SLM_KEY"]), shell=True)
