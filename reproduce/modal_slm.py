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

The GPU spins up on the first request and shuts down after SCALEDOWN seconds
of silence, so an idle deployment costs nothing.
"""

import modal

MODEL = "Qwen/Qwen2.5-3B-Instruct"   # the paper's row: 48.75% acc / 26.02% err
GPU = "A10G"                          # 24 GB: fits the 3B in bf16 with room for KV cache
PORT = 8000
SCALEDOWN = 300                       # idle seconds before the GPU is released

# Context has to clear the real prompt sizes: measured on this project's index,
# the retrieved context is 3,908 tokens at the median and 8,291 at the maximum,
# before the Entities table and the prompt template are added.
MAX_MODEL_LEN = 32768   # Qwen2.5-3B hỗ trợ 32k; để dư sau sự cố tràn 16.413 token

app = modal.App("minirag-slm")

vllm_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("vllm==0.11.0", "huggingface_hub[hf_transfer]==0.35.3")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})
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
    import os
    import subprocess

    subprocess.Popen(" ".join([
        "vllm serve", MODEL,
        "--served-model-name", MODEL, "minirag-slm",
        "--host 0.0.0.0", f"--port {PORT}",
        f"--max-model-len {MAX_MODEL_LEN}",
        "--api-key", os.environ["MINIRAG_SLM_KEY"],
        "--disable-log-requests",
    ]), shell=True)
