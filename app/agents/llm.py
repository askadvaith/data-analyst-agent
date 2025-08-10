import os
from typing import List, Dict, Any
try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover - dev env without package
    genai = None  # type: ignore

# IMPORTANT: Use Gemini models for LLM operations.
# - Use 2.5-flash for non-coding reasoning or short planning
# - Use 2.5-pro for coding operations

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def _has_real_key() -> bool:
    if not GEMINI_API_KEY:
        return False
    lower = GEMINI_API_KEY.strip().lower()
    if lower in {"test", "dummy", "placeholder"} or lower.startswith("test_"):
        return False
    return True


if _has_real_key() and genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)


def get_model(name: str):
    if not _has_real_key() or genai is None:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.GenerativeModel(name)


def generate_plain(prompt: str, model: str = "gemini-2.5-flash") -> str:
    if not _has_real_key() or genai is None:
        # Local dev fallback: return empty so callers use their default plans
        return ""
    try:
        m = get_model(model)
        resp = m.generate_content(prompt)
        return resp.text or ""
    except Exception:
        # Any error -> fallback to empty so planner uses default plan
        return ""


def generate_code(prompt: str, files: Dict[str, bytes] | None = None, timeout: int = 60) -> str:
    # For coding, use 2.5-pro
    if not _has_real_key() or genai is None:
        # Local dev fallback: simple script that prints a safe stub JSON
        return (
            "import json\n"
            "print(json.dumps(['stub']))\n"
        )
    try:
        m = get_model("gemini-2.5-pro")
        parts = [prompt]
        # Attach files as input references when small; otherwise, summarize separately upstream
        if files:
            for name, content in files.items():
                try:
                    # Use inline text for small files (<150KB)
                    if len(content) <= 150_000:
                        parts.append(f"\n\n# Attachment: {name}\n" + content.decode("utf-8", errors="ignore"))
                except Exception:
                    pass
        resp = m.generate_content(parts)
        return resp.text or ""
    except Exception:
        return (
            "import json\n"
            "print(json.dumps(['stub']))\n"
        )
