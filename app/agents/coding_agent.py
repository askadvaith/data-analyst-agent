from __future__ import annotations
from typing import Dict, Any
from textwrap import dedent
from app.agents.llm import generate_code
from app.utils.logger import LogSession


class CodeGenError(Exception):
    pass


async def generate_code_for_task(task, timeout: int = 60, logger: LogSession | None = None, mode: str = "code", feedback: str | None = None) -> str:
    """Generate code for a task, optionally incorporating feedback from previous attempts."""
    
    # Build mode-specific system prompt
    if mode == "source":
        sys = dedent(
            """
            You are a senior data engineer. Generate a single, self-contained Python script that:
            - SOURCES data only (do not answer the user's questions here).
            - Uses the injected variables: attachments (Dict[str, bytes]) and questions_txt (str).
            - If URLs are referenced in questions_txt, download the full HTML/text content using requests/httpx with proper User-Agent headers.
            - If files are in attachments, read them fully (text files as strings; tabular files with pandas including raw text).
            - If S3 URLs or cloud storage paths are mentioned, use s3fs which is available in the environment.
            - If database schema/connection info is provided, execute targeted SELECT queries for only relevant columns/rows.
            - Return a SINGLE JSON object mapping source names to their full contents (strings for HTML/text; arrays/objects for tables).
            - Print ONLY this JSON object to stdout.
            - Available libraries: requests, httpx, pandas, s3fs, duckdb, pyarrow, bs4, lxml
            - No external API keys required (except for standard web access).
            - Enforce a 90s overall runtime; be efficient.
            
            Implementation tips:
            - Use requests with timeouts and headers: {'User-Agent': 'Mozilla/5.0 (compatible; DataBot/1.0)'}
            - Handle redirects and HTTP failures gracefully, include error messages in JSON if sources fail.
            - For robustness, wrap each data source fetch in try-except blocks.
            """
        )
    else:
        sys = dedent(
            """
            You are a senior data engineer. Generate a single, self-contained Python script that:
            - Uses the injected variables: attachments (Dict[str, bytes]) and questions_txt (str).
            - If URLs are mentioned in questions_txt, fetch them using requests/httpx with proper headers and timeouts.
            - If files are in attachments, read and process them (text files as strings, CSV/Excel/Parquet with pandas).
            - Has access to libraries: pandas, numpy, matplotlib, seaborn, bs4, lxml, duckdb, pyarrow, s3fs, requests, httpx, html5lib
            - Produces exactly the final answers in the requested format (JSON array/object). 
            - For plots: save as PNG, convert to base64 data URI under 100kB, include in JSON response.
            - Prints ONLY the final JSON string to stdout.
            - No external API keys required (except for standard web scraping).
            - Enforce a 120s overall runtime; be efficient.

            Key implementation guidelines:
            - For web scraping: Use proper User-Agent headers and handle timeouts/redirects gracefully.
            - For data cleaning: Remove currency symbols, commas, NBSP, footnote markers before converting to numeric.
            - For HTML parsing: Scan all tables and pick by header matching or content heuristics.
            - For S3/cloud data: Use s3fs library which is available in the environment.
            - Use deterministic operations (sorted keys/rows) when selecting from ties.
            - Handle missing or malformed data gracefully with appropriate error messages in JSON.

            - IMPORTANT: For DuckDB SQL, DO NOT use julianday(). To calculate the difference in days between two dates, use DATE_DIFF('day', try_strptime(date_of_registration, '%d-%m-%Y'), decision_date).
            """
        )

    user = dedent(
        f"""
        TASK INSTRUCTIONS:\n{task.instructions}\n\nCONTEXT:\n{task.context}
        """
    )
    
    # Add feedback if this is a retry
    if feedback:
        user += f"\n\nFEEDBACK FROM PREVIOUS ATTEMPT:\n{feedback}\n\nPlease fix the issues mentioned in the feedback and regenerate the code."

    prompt = sys + "\n\n" + user
    code = generate_code(prompt, logger=logger)
    if not code:
        raise CodeGenError("Empty code from model")
    
    # Check if we got stub code and log it
    if "print(json.dumps(['stub']))" in code:
        if logger:
            logger.log("WARNING: Generated code contains stub placeholder")
        raise CodeGenError("Generated stub code instead of real implementation")
    
    # Extract python code fences if present
    import re
    m = re.findall(r"```python\n(.*?)```", code, re.S)
    if m:
        code = m[-1]

    return code
