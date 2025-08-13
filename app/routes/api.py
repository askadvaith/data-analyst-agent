import io
import os
import time
from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import cast
from fastapi.responses import JSONResponse
from app.agents.pipeline import run_pipeline
from app.utils.logger import new_log_session

router = APIRouter()

# Health check route for GET requests
@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "API is healthy"}

@router.post("/")
async def analyze(request: Request):
    started = time.time()
    questions: str | None = None
    attachments: Dict[str, bytes] = {}

    # Parse any form fields to support arbitrary field names and providers
    # that may set either the field name or filename to "questions.txt".
    try:
        form = await request.form()
    except Exception as e:
        raise HTTPException(status_code=400, detail="multipart/form-data with questions.txt is required")

    if form:
        # Read all uploaded files once into memory
        files: list[dict[str, Any]] = []
        for key, value in form.multi_items():
            is_file_like = hasattr(value, "filename") and hasattr(value, "read")
            if not is_file_like:
                continue
            uf = cast(UploadFile, value)
            content = await uf.read()
            files.append({
                "field": key or "",
                "filename": uf.filename or "",
                "content": content,
            })

        # Identify questions.txt by field name OR filename, case-insensitive
        q_index: int | None = None
        for i, f in enumerate(files):
            if f["field"].lower() == "questions.txt" or f["filename"].lower() == "questions.txt":
                q_index = i
                break

        if q_index is not None:
            questions_bytes = files[q_index]["content"]
            questions = questions_bytes.decode("utf-8", errors="ignore")
        # Strict per spec: questions.txt must be present

        # Build attachments from the remainder
        for i, f in enumerate(files):
            if i == q_index:
                continue
            name = f["filename"] or f["field"] or f"file_{i}"
            attachments[name] = f["content"]

    if not questions or not questions.strip():
        raise HTTPException(status_code=400, detail="questions.txt is required")

    try:
        # LOGGING CODE: create a per-request log session
        log = new_log_session(file_prefix="api")
        log.log("Received request with questions.txt and attachments: " + ", ".join(attachments.keys()))
        # LOGGING CODE: log a short preview of questions
        log.log("questions.txt preview: " + questions[:300].replace("\n", " "))

        result = await run_pipeline(questions, attachments, deadline_secs=290, logger=log)  # 280s to leave 20s buffer under 5 minutes
        # LOGGING CODE: log final result (full)
        try:
            log.log("Final result (full):\n" + str(result))
        except Exception:
            pass
    except Exception as e:
        # LOGGING CODE: record exception before surfacing
        try:
            detail = str(e) or repr(e)
        except Exception:
            detail = ""
        try:
            log = locals().get("log")
            if log:
                log.log("ERROR: " + detail)
        except Exception:
            pass
        # Surface richer error details to aid debugging without leaking internals
        raise HTTPException(status_code=500, detail=detail)

    elapsed = time.time() - started
    return JSONResponse(content=result, headers={"X-Elapsed": str(round(elapsed, 3))})
