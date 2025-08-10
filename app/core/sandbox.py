from __future__ import annotations
import asyncio
import json
import sys
import subprocess
from typing import Dict, Any, Optional
import tempfile
import os


def _build_script(code: str, attachments: Dict[str, bytes], questions_txt: Optional[str], sourced_data: Optional[Any]) -> str:
    # Construct script via concatenation to avoid .format interfering with user braces
    prefix = (
        "# Auto-generated execution harness\n"
        "import sys, io, json, base64\n"
        "from typing import Dict\n\n"
        "attachments: Dict[str, bytes] = {}\n"
        "# Attachments injected below\n"
    )
    inject = "\n".join([f"attachments[{k!r}] = {v!r}" for k, v in attachments.items()])
    q_section = "\nquestions_txt = ''\n"
    if questions_txt is not None:
        import base64 as _b64
        b = _b64.b64encode(questions_txt.encode('utf-8')).decode('ascii')
        q_section = (
            "\n# Inject questions_txt\n"
            f"_qt_b64 = '{b}'\n"
            "questions_txt = base64.b64decode(_qt_b64).decode('utf-8', 'ignore')\n"
        )
    sd_section = "\nsourced_data = None\n"
    if sourced_data is not None:
        try:
            import json as _json
            sd_json = _json.dumps(sourced_data)
        except Exception:
            sd_json = "null"
        # Use base64 to avoid quoting issues in large JSON strings
        import base64 as _b64
        sd_b64 = _b64.b64encode(sd_json.encode('utf-8')).decode('ascii')
        sd_section = (
            "\n# Inject sourced_data (JSON-deserialized)\n"
            f"_sd_b64 = '{sd_b64}'\n"
            "sourced_data = json.loads(base64.b64decode(_sd_b64).decode('utf-8', 'ignore'))\n"
        )
    start = "\n\n# User code starts\n"
    return prefix + inject + q_section + sd_section + start + code + "\n"


async def run_python_in_sandbox(code: str, attachments: Dict[str, bytes], questions_txt: Optional[str] = None, sourced_data: Optional[Any] = None, timeout: int = 60) -> Dict[str, Any]:
    script = _build_script(code, attachments, questions_txt, sourced_data)

    # Execute via blocking subprocess.run inside a worker thread for broad Windows compatibility.
    # Write the script to a temporary file to avoid Windows command-line length limits with `-c`.
    def _run() -> tuple[int, bytes, bytes, str | None]:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".py", encoding="utf-8") as tmp:
                tmp.write(script)
                tmp_path = tmp.name

            completed = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            return completed.returncode, completed.stdout, completed.stderr, None
        except subprocess.TimeoutExpired:
            return 1, b"", b"timeout", "timeout"
        except Exception as exc:
            # Bubble up error string via stderr
            return 1, b"", str(exc).encode("utf-8", "ignore"), str(exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    returncode, stdout, stderr, errflag = await asyncio.to_thread(_run)

    out = stdout.decode("utf-8", errors="ignore")
    err = stderr.decode("utf-8", errors="ignore")
    data = {"ok": returncode == 0 and errflag is None, "stdout": out, "stderr": err}
    try:
        data["stdout_json"] = json.loads(out)
    except Exception:
        data["stdout_json"] = None
    return data
