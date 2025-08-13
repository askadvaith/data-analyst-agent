import os
import logging
import asyncio
from typing import Dict, Any

# --- Original Gemini implementation (commented out, preserved per requirement) ---
"""
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - dev env without package
    genai = None  # type: ignore

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def _has_real_key() -> bool:
    if not GEMINI_API_KEY:
        return False
    lower = GEMINI_API_KEY.strip().lower()
    if lower in {"test", "dummy", "placeholder"} or lower.startswith("test_"):
        return False
    return True

if _has_real_key() and genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)  # type: ignore

def get_model(name: str):
    if not _has_real_key() or genai is None:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.GenerativeModel(name)  # type: ignore

def _gemini_generate_plain(prompt: str, model: str = "gemini-2.5-flash", timeout: int = 30) -> str:
    # (Original implementation)
    return ""

def _gemini_generate_code(prompt: str, files: Dict[str, bytes] | None = None, timeout: int = 60, logger=None) -> str:
    return "import json\nprint(json.dumps(['stub']))\n"
"""
# ------------------------------------------------------------------------------

# OpenAI via AI Pipe proxy integration.
# Usage environment variables (as per AI Pipe docs):
#   OPENAI_API_KEY   -> AI Pipe token
#   OPENAI_BASE_URL  -> https://aipipe.org/openai/v1 (defaulted if unset)

AI_PIPE_API_KEY = os.getenv("OPENAI_API_KEY")
AI_PIPE_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")

_openai_client = None
try:
    if AI_PIPE_API_KEY:
        from openai import OpenAI  # type: ignore
        _openai_client = OpenAI(api_key=AI_PIPE_API_KEY, base_url=AI_PIPE_BASE_URL)
except Exception:
    _openai_client = None  # pragma: no cover


def _has_openai() -> bool:
    return _openai_client is not None and bool(AI_PIPE_API_KEY)


def _map_model(model: str, purpose: str) -> str:
    """Map legacy Gemini model names to OpenAI (AI Pipe proxied) models."""
    lower = (model or "").lower()
    if "pro" in lower or purpose == "code":
        return "gpt-4o-mini"  # balanced for coding tasks
    return "gpt-4.1-nano"  # fast, cheap default


def generate_plain(prompt: str, model: str = "gemini-2.5-flash", timeout: int = 30) -> str:
    """Generate plain text using OpenAI Responses API via AI Pipe.

    Falls back to empty string if unavailable (callers already have fallbacks).
    The model parameter is accepted for backward compatibility; Gemini names are mapped.
    """
    if not prompt:
        return ""
    if not _has_openai():
        return ""
    target_model = _map_model(model, purpose="plain")

    import concurrent.futures

    def _call():
        try:
            resp = _openai_client.responses.create(  # type: ignore[attr-defined]
                model=target_model,
                input=prompt,
            )
            # New Responses API: aggregate text parts
            texts: list[str] = []
            for item in getattr(resp, "output", []) or []:  # type: ignore
                for c in getattr(item, "content", []) or []:
                    t = getattr(c, "text", None)
                    if t and getattr(t, "value", None):
                        texts.append(t.value)
            if not texts and hasattr(resp, "output_text"):
                try:
                    return resp.output_text  # type: ignore
                except Exception:
                    pass
            return "\n".join(texts)
        except Exception:
            return ""

    with concurrent.futures.ThreadPoolExecutor() as ex:
        fut = ex.submit(_call)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            return ""


def generate_code(prompt: str, files: Dict[str, bytes] | None = None, timeout: int = 60, logger=None) -> str:
    """Generate code using OpenAI via AI Pipe.

    Returns stub code if unavailable.
    """
    if not prompt:
        return "import json\nprint(json.dumps(['stub']))\n"

    # Append small file contents inline to help the model.
    if files:
        for name, content in files.items():
            try:
                if len(content) <= 120_000:
                    snippet = content.decode("utf-8", errors="ignore")
                    prompt += f"\n\n# FILE: {name}\n{snippet}\n"
            except Exception:
                pass

    if not _has_openai():
        if logger:
            logger.log("Returning stub code: OpenAI (AI Pipe) client not available")
        return "import json\nprint(json.dumps(['stub']))\n"

    model = _map_model("gemini-2.5-pro", purpose="code")

    import concurrent.futures

    def _call():
        try:
            resp = _openai_client.responses.create(  # type: ignore[attr-defined]
                model=model,
                input=prompt,
            )
            texts: list[str] = []
            for item in getattr(resp, "output", []) or []:  # type: ignore
                for c in getattr(item, "content", []) or []:
                    t = getattr(c, "text", None)
                    if t and getattr(t, "value", None):
                        texts.append(t.value)
            code = "\n".join(texts)
            return code or "import json\nprint(json.dumps(['stub']))\n"
        except Exception as e:
            if logger:
                logger.log(f"Returning stub code: Exception {e}")
            return "import json\nprint(json.dumps(['stub']))\n"

    with concurrent.futures.ThreadPoolExecutor() as ex:
        fut = ex.submit(_call)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            if logger:
                logger.log("Returning stub code: OpenAI call timed out")
            fut.cancel()
            return "import json\nprint(json.dumps(['stub']))\n"
