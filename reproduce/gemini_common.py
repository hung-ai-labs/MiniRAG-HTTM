"""Shared MiniRAG-over-Gemini setup for the reproduce scripts."""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from minirag import MiniRAG  # noqa: E402
from minirag.llm.gemini import (  # noqa: E402
    _resolve_api_keys,
    gemini_complete,
    gemini_embed,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
)
from minirag.llm.hf import hf_embed  # noqa: E402
from minirag.utils import EmbeddingFunc  # noqa: E402


def get_args(description="MiniRAG + Gemini"):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-flash-lite-latest",
        help="Gemini chat model, e.g. gemini-flash-lite-latest / gemini-3.6-flash",
    )
    parser.add_argument(
        "--embedmodel", type=str, default="local",
        help='"local" runs sentence-transformers/all-MiniLM-L6-v2 on this '
             "machine (what the MiniRAG paper uses, and it spends no API "
             "quota); anything else is treated as a Gemini embedding model.",
    )
    parser.add_argument("--outputpath", type=str, default="./logs/Default_output.csv")
    parser.add_argument("--workingdir", type=str, default="./LiHua-World")
    parser.add_argument("--datapath", type=str, default="./dataset/LiHua-World/data/")
    parser.add_argument(
        "--querypath", type=str, default="./dataset/LiHua-World/qa/query_set.csv"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process the first N documents/questions (0 = all). "
        "Useful to stay inside Gemini free-tier rate limits.",
    )
    parser.add_argument(
        "--evidence",
        action="store_true",
        help="Index only the documents the query set's Evidence column points "
        "at, instead of the first N files on disk. Without this a subset of "
        "documents and a subset of questions barely overlap, and accuracy "
        "measures corpus coverage rather than retrieval quality.",
    )
    return parser.parse_args()


def build_rag(args):
    try:
        keys = _resolve_api_keys()
    except ValueError as e:
        raise SystemExit(
            f"{e}\nPut the key(s) in the .env file at the repo root."
        )
    print(f"USING {len(keys)} API KEY(S)")

    os.makedirs(args.workingdir, exist_ok=True)
    print("USING LLM:", args.model)
    print("USING EMBEDDING:", args.embedmodel)
    print("USING WORKING DIR:", args.workingdir)

    # Embeddings run locally by default. Sharing one project quota between
    # chat and embeddings starved the embedding calls, and MiniRAG treats an
    # embedding failure as fatal to the whole document.
    if args.embedmodel == "local":
        from transformers import AutoModel, AutoTokenizer

        local_name = "sentence-transformers/all-MiniLM-L6-v2"
        tokenizer = AutoTokenizer.from_pretrained(local_name)
        embed_model = AutoModel.from_pretrained(local_name)
        embedding = EmbeddingFunc(
            embedding_dim=384,
            max_token_size=1000,
            func=lambda texts: hf_embed(
                texts, tokenizer=tokenizer, embed_model=embed_model
            ),
        )
    else:
        embedding = EmbeddingFunc(
            embedding_dim=DEFAULT_EMBEDDING_DIM,
            max_token_size=1000,
            func=lambda texts: gemini_embed(texts, model=args.embedmodel),
        )

    return MiniRAG(
        working_dir=args.workingdir,
        llm_model_func=gemini_complete,
        llm_model_max_token_size=200,
        llm_model_name=args.model,
        llm_model_max_async=8,
        embedding_func_max_async=4,
        embedding_func=embedding,
    )
