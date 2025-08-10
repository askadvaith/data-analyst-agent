from __future__ import annotations
from typing import Dict, Any
from textwrap import dedent
from app.agents.llm import generate_code
from app.utils.logger import LogSession


class CodeGenError(Exception):
    pass


async def generate_code_for_task(task, timeout: int = 60, logger: LogSession | None = None, mode: str = "code") -> str:
    # Build mode-specific system prompt
    if mode == "source":
        sys = dedent(
            """
            You are a senior data engineer. Generate a single, self-contained Python script that:
            - SOURCES data only (do not answer the user's questions here).
            - Reads 'questions_txt' and any provided attachments from a provided dict attachments: Dict[str, bytes]
            - If URLs are referenced, fetch the full HTML/text content (use a proper User-Agent) without assuming table names/structure before scraping.
            - If files are attached, read them fully (text or tabular via pandas); include raw bytes/text as needed.
            - If a database schema is provided, issue targeted SELECT queries for only relevant columns/rows (avoid scanning entire DB).
            - Return a SINGLE JSON object mapping source names to their full contents (strings for HTML/text; arrays/objects for tables); print ONLY this JSON to stdout.
            - Do not require external API keys.
            - Enforce a 90s overall runtime; be efficient.
            Implementation tips:
            - Use requests/httpx with timeouts and headers.
            - For robustness, handle redirects/HTTP failures gracefully and include error strings in the JSON if a source fails.
            """
        )
    else:
        sys = dedent(
            """
            You are a senior data engineer. Generate a single, self-contained Python script that:
            - Uses the injected variables sourced_data (JSON-like), attachments (Dict[str, bytes]), and questions_txt (str).
            - Treat sourced_data as the PRIMARY data context; DO NOT perform any network calls or re-fetch data when sourced_data exists.
            - Do not attempt to read from files, stdin, special file descriptors, or environment variables provided by the runner; rely only on the injected variables above.
            - Uses libraries: pandas, numpy, matplotlib, bs4, lxml, duckdb/pyarrow when needed
            - Produces exactly the final answers in the requested format (JSON array/object). If a plot is requested, return base64 data URI under 100kB.
            - Prints ONLY the final JSON string to stdout.
            - Do not require external API keys; no web calls unless explicitly no sourced_data is available.
            - Enforce a 120s overall runtime; be efficient.
            Robustness rules:
            - Do not assume table positions/names; if parsing HTML in sourced_data, scan all tables and pick by header match/heuristics.
            - When cleaning currency/number fields, remove all non-digit/decimal characters (e.g., $, commas, NBSP, footnote markers, daggers) and use pd.to_numeric(errors='coerce').
            - Use deterministic operations (sorted keys/rows) when selecting from ties.
            - Prefer sourced_data.get('_primary_html') for HTML parsing if present; else choose the first value in sourced_data that looks like HTML.
            - Treat optional columns like 'Peak' defensively: if absent, compute answers that don't need it and set correlation to null.
            """
        )

    user = dedent(
        f"""
        TASK INSTRUCTIONS:\n{task.instructions}\n\nCONTEXT:\n{task.context}
        """
    )

    prompt = sys + "\n\n" + user
    code = generate_code(prompt)
    if not code:
        raise CodeGenError("Empty code from model")
    # Extract python code fences if present
    import re
    m = re.findall(r"```python\n(.*?)```", code, re.S)
    if m:
        code = m[-1]

    # LOGGING CODE: log the full extracted/generated code
    if logger:
        try:
            logger.log(f"Full generated code for {getattr(task, 'id', '?')}:\n" + code)
        except Exception:
            pass
    return code
