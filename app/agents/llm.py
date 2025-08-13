import os
import logging
import asyncio
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
    genai.configure(api_key=GEMINI_API_KEY)  # type: ignore


def get_model(name: str):
    if not _has_real_key() or genai is None:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.GenerativeModel(name)  # type: ignore


def generate_plain(prompt: str, model: str = "gemini-2.5-flash", timeout: int = 30) -> str:
    """Generate plain text response with timeout control."""
    if not _has_real_key() or genai is None:
        # Local dev fallback: return empty so callers use their default plans
        return ""
    try:
        # Use asyncio to enforce timeout
        import concurrent.futures
        import threading
        
        def _generate():
            m = get_model(model)
            resp = m.generate_content(prompt)
            return resp.text or ""
        
        # Run with timeout
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_generate)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                # Cancel the future and return empty response
                future.cancel()
                return ""
    except Exception:
        # Any error -> fallback to empty so planner uses default plan
        return ""


def generate_code(prompt: str, files: Dict[str, bytes] | None = None, timeout: int = 60, logger=None) -> str:
    # For coding, use 2.5-pro
    if not _has_real_key():
        stub_reason = "GEMINI_API_KEY not set or is a test key"
        if logger:
            logger.log(f"Returning stub code: {stub_reason}")
        return (
            "import json\n"
            "print(json.dumps(['stub']))\n"
        )
    
    if genai is None:
        stub_reason = "google.generativeai module not available"
        if logger:
            logger.log(f"Returning stub code: {stub_reason}")
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
        
        # Check if response was blocked by safety filters or other reasons
        if not resp.candidates:
            stub_reason = "LLM response was blocked (no candidates returned)"
            if logger:
                logger.log(f"Returning stub code: {stub_reason}")
            return (
                "import json\n"
                "print(json.dumps(['stub']))\n"
            )
        
        candidate = resp.candidates[0]
        if hasattr(candidate, 'finish_reason') and candidate.finish_reason != 1:  # 1 = STOP (success)
            finish_reasons = {
                2: "MAX_TOKENS",
                3: "SAFETY", 
                4: "RECITATION",
                5: "OTHER"
            }
            reason_name = finish_reasons.get(candidate.finish_reason, f"UNKNOWN({candidate.finish_reason})")
            stub_reason = f"LLM response blocked due to finish_reason: {reason_name}"
            if logger:
                logger.log(f"Returning stub code: {stub_reason}")
            return (
                "import json\n"
                "print(json.dumps(['stub']))\n"
            )
        
        # Safely get the text content
        generated_code = ""
        try:
            generated_code = resp.text or ""
        except Exception as text_error:
            stub_reason = f"Failed to extract text from LLM response: {str(text_error)}"
            if logger:
                logger.log(f"Returning stub code: {stub_reason}")
            return (
                "import json\n"
                "print(json.dumps(['stub']))\n"
            )
        
        # Check if the generated code is empty or just whitespace
        if not generated_code.strip():
            stub_reason = "LLM returned empty response"
            if logger:
                logger.log(f"Returning stub code: {stub_reason}")
            return (
                "import json\n"
                "print(json.dumps(['stub']))\n"
            )
        
        # Log successful code generation
        if logger:
            logger.log(f"Successfully generated {len(generated_code)} characters of code")
        
        return generated_code
        
    except Exception as e:
        stub_reason = f"Exception during LLM code generation: {str(e)}"
        if logger:
            logger.log(f"Returning stub code: {stub_reason}")
        return (
            "import json\n"
            "print(json.dumps(['stub']))\n"
        )
