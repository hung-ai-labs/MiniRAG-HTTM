# Backends are imported lazily-tolerantly: a missing optional dependency for one
# provider must not break the others (e.g. no torch/transformers installed when
# only the Gemini API is used).

try:
    from minirag.llm.openai import gpt_4o_mini_complete  # noqa: F401
except ImportError:  # pragma: no cover
    pass

try:
    from minirag.llm.gemini import (  # noqa: F401
        gemini_complete,
        gemini_complete_if_cache,
        gemini_flash_lite_complete,
        gemini_flash_complete,
        gemini_embed,
    )
except ImportError:  # pragma: no cover
    pass

try:
    from minirag.llm.hf import hf_embed, hf_model_complete  # noqa: F401
except ImportError:  # pragma: no cover
    pass
