from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

from app.agents.llm import generate_plain
from app.utils.logger import LogSession


@dataclass
class Task:
    id: str
    kind: str  # 'code' | 'fetch' | 'analyze' (we'll use 'code' primary)
    instructions: str
    context: Dict[str, Any]


@dataclass
class Plan:
    tasks: List[Task]
    format_hint: str | None = None


async def parse_tasks(questions_txt: str, attachments: Dict[str, bytes], timeout: int = 30, logger: LogSession | None = None) -> Plan:
    # Use gemini-2.5-flash to draft a plan with a first 'source' task followed by analysis tasks.
    prompt = f"""
You are a task planner. Given questions.txt and optional attachments (names only), create a two-phase plan:
1) First task must be kind:'source' that collects ALL relevant data required by the remaining tasks. It can:
   - Scrape webpages (fetch the full HTML/content first; don't assume table structure before scraping).
   - Read attached files via code.
   - Query a backend database using a provided schema (if present in questions or attachments); only query relevant columns/rows, not the whole DB.
   The 'source' task must return a single JSON object with keys indicating sources and the full collected content or datasets.
2) Then 1-3 kind:'code' tasks to transform/analyze and produce the final answer.

Output JSON: {{
  "tasks": [{{"id": "source1", "kind": "source", "instructions": "...", "context": {{"attachments": [...], "questions_excerpt": "...", "db_schema": "<if any>"}} }},
             {{"id": "task2", "kind": "code", "instructions": "...", "context": {{}} }}],
  "format_hint": "json object|array|..."
}}

Keep total tasks 2-4. Include any database schema text you see under context.db_schema. Never skip the 'source' task.

questions.txt:\n---\n{questions_txt}\n---\nattachments:\n{list(attachments.keys())}
"""
    try:
        plan_text = generate_plain(prompt, model="gemini-2.5-flash")
    except Exception:
        # Fallback minimal single code task if LLM unavailable
        plan_text = ""

    # LOGGING CODE: record raw plan text preview
    if logger:
        try:
            prev = plan_text[:800].replace("\n", " ")
            logger.log("Planner raw output: " + prev)
        except Exception:
            pass

    tasks: List[Task] = []
    format_hint: str | None = None

    # Simple robust parse: try JSON first; if fails, make a single code task
    import json
    try:
        # LOGGING CODE: strip markdown code fences if present
        txt = plan_text.strip()
        if txt.startswith("```"):
            # remove first fence line and trailing fence
            lines = [ln for ln in txt.splitlines() if not ln.strip().startswith("```")]
            txt = "\n".join(lines)
        data = json.loads(txt)
        for i, t in enumerate(data.get("tasks", [])):
            tasks.append(Task(
                id=str(t.get("id", f"task{i+1}")),
                kind=str(t.get("kind", "code")),
                instructions=str(t.get("instructions", "")),
                context=dict(t.get("context", {})),
            ))
        format_hint = data.get("format_hint")
    except Exception:
        # Minimal default: two tasks (source then analyze) if LLM unavailable
        tasks.append(Task(
            id="source1",
            kind="source",
            instructions=(
                "Collect all data required: \n"
                "- If URLs appear in questions_txt, download full HTML/content for each.\n"
                "- Load any attached files into memory.\n"
                "- If a DB schema is described, prepare targeted SELECTs to fetch only relevant rows/columns.\n"
                "Return a JSON object mapping source names to their full contents or data."
            ),
            context={"attachments": list(attachments.keys()), "questions_txt": questions_txt[:4000]},
        ))
        tasks.append(Task(
            id="task2",
            kind="code",
            instructions="Use the sourced_data/sourced_json to answer the user questions and print only the final JSON.",
            context={"questions_txt": questions_txt[:4000]},
        ))

    if not tasks:
        tasks.append(Task(id="task1", kind="code", instructions="Solve questions", context={}))

    return Plan(tasks=tasks, format_hint=format_hint)
