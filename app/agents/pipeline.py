import asyncio
import json
import time
from typing import Dict, Any
from app.utils.logger import LogSession

from app.agents.task_parser import parse_tasks
from app.agents.coding_agent import generate_code_for_task
from app.agents.aggregator import aggregate_answers
from app.core.sandbox import run_python_in_sandbox


async def run_pipeline(questions_txt: str, attachments: Dict[str, bytes], deadline_secs: int = 170, logger: LogSession | None = None) -> Any:
    start = time.time()
    remaining = lambda: max(5, deadline_secs - int(time.time() - start))

    # LOGGING CODE: log pipeline start
    if logger:
        logger.log("Pipeline start; computing task plan")

    plan = await parse_tasks(questions_txt, attachments, timeout=remaining(), logger=logger)

    # LOGGING CODE: log parsed tasks
    if logger:
        try:
            logger.log("Parsed tasks: " + json.dumps([t.__dict__ for t in plan.tasks])[:1200])
        except Exception:
            logger.log("Parsed tasks (non-JSON)")

    task_outputs: Dict[str, Any] = {}
    sourced_data: Any | None = None
    # Execute tasks sequentially to keep control on time; force 'source' first if present
    for idx, task in enumerate(plan.tasks):
        if remaining() <= 5:
            break
        if task.kind == "source":
            # Generate source code that collects and returns a JSON object with all required datasets
            instructions = (
                "Write Python to SOURCE data per instructions. Requirements:\n"
                "- If URLs are referenced, download the entire HTML/text and include under keys by URL.\n"
                "- If files are attached (available in attachments dict), read them fully; for tabular files parse with pandas; include raw text too.\n"
                "- If a database schema is provided, build targeted SELECTs to fetch only relevant data; do not scan entire DB.\n"
                "- Return a single JSON object mapping source names to contents (strings for HTML/text; JSON arrays/objects for tables).\n"
                "- Print only the final JSON to stdout."
            )
            src_task = type("T", (), {"instructions": instructions + "\n\nUSER CONTEXT:\n" + str(task.context), "context": task.context, "id": task.id})
            code = await generate_code_for_task(src_task, timeout=min(60, remaining()), logger=logger, mode="source")
            if logger:
                logger.log("Executing source task code")
            result = await run_python_in_sandbox(code, attachments, questions_txt=questions_txt, sourced_data=None, timeout=min(60, remaining()))
            task_outputs[task.id] = result
            # Attempt to parse JSON from stdout into sourced_data
            try:
                if isinstance(result, dict) and result.get("stdout_json") is not None:
                    sourced_data = result.get("stdout_json")
                else:
                    import json as _json
                    sourced_data = _json.loads(result.get("stdout") or "null")
            except Exception:
                sourced_data = None
            # Heuristics: enrich sourced_data with convenience keys for downstream analysis
            if isinstance(sourced_data, dict):
                try:
                    html_candidates = []
                    text_blobs = []
                    for k, v in sourced_data.items():
                        if isinstance(v, str):
                            lv = v.lower()
                            if ("<html" in lv) or ("<table" in lv) or ("<div" in lv and "wikitable" in lv):
                                html_candidates.append(v)
                            if len(v) > 500:
                                text_blobs.append(v)
                    if html_candidates and "_primary_html" not in sourced_data:
                        sourced_data["_primary_html"] = html_candidates[0]
                    if text_blobs and "_text_blobs" not in sourced_data:
                        sourced_data["_text_blobs"] = text_blobs
                except Exception:
                    pass
            if logger:
                logger.log("Sourced data keys: " + ", ".join(sorted((sourced_data or {}).keys())) if isinstance(sourced_data, dict) else ("type=" + type(sourced_data).__name__))
            continue

        if task.kind == "code":
            code = await generate_code_for_task(task, timeout=min(60, remaining()), logger=logger, mode="code")
            # LOGGING CODE: log generated code size
            if logger:
                logger.log(f"Generated code for {task.id}: {len(code)} bytes")
            result = await run_python_in_sandbox(code, attachments, questions_txt=questions_txt, sourced_data=sourced_data, timeout=min(60, remaining()))
            # LOGGING CODE: log sandbox outputs and errors
            if logger:
                try:
                    ok = result.get("ok")
                    stdout = result.get("stdout") or ""
                    stderr = result.get("stderr") or ""
                    if ok:
                        prev = stdout if len(stdout) <= 400 else stdout[:400] + "..."
                        logger.log(f"Sandbox OK for {task.id}; stdout preview: {prev}")
                    else:
                        # LOGGING CODE: include the FULL error message thrown by the generated code (no trimming)
                        logger.log(f"Sandbox ERROR for {task.id}; stderr (full):\n{stderr}")
                except Exception:
                    pass
            task_outputs[task.id] = result
        else:
            # Non-code tasks may be pre-answered by the parser/LLM; keep placeholder
            task_outputs[task.id] = {"status": "skipped", "reason": "non-code"}

    output = aggregate_answers(plan, task_outputs, attachments, logger=logger)
    # LOGGING CODE: log full aggregated answer
    if logger:
        try:
            logger.log("Aggregated output (full):\n" + str(output))
        except Exception:
            pass
    return output
