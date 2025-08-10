from __future__ import annotations
import json
from typing import Dict, Any
from dataclasses import dataclass

from app.agents.task_parser import Plan
from app.utils.logger import LogSession


def aggregate_answers(plan: Plan, task_outputs: Dict[str, Any], attachments: Dict[str, bytes], logger: LogSession | None = None):
    # Prefer outputs from non-source code tasks; never return the raw 'source' output as final.
    for task in reversed(plan.tasks):
        if getattr(task, "kind", "code") == "source":
            continue
        out = task_outputs.get(task.id)
        if isinstance(out, dict) and out.get("ok") and out.get("stdout_json") is not None:
            # LOGGING CODE: log selection rationale
            if logger:
                logger.log(f"Aggregator picked stdout_json from {task.id}")
            return out["stdout_json"]
        if isinstance(out, dict) and out.get("stdout"):
            try:
                if logger:
                    logger.log(f"Aggregator picked stdout text from {task.id}")
                return json.loads(out["stdout"])
            except Exception:
                pass

    if logger:
        logger.log("Aggregator produced error: No valid output produced")
    return {"error": "No valid output produced"}
