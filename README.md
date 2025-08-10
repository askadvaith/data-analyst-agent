Data Analyst Agent API
======================

FastAPI service that accepts multipart POST with `questions.txt` and optional attachments, plans tasks with Gemini, generates Python code to execute analysis in a sandbox, and returns answers in the requested JSON format within ~3 minutes.

Quick start (local)
-------------------
1. Set `GEMINI_API_KEY` in your environment.
2. Install deps and run:

	 - With uv:
		 - `uv sync`
		 - `uv run uvicorn app.main:app --reload`

	 - With pip:
		 - `pip install -e .`
		 - `uvicorn app.main:app --reload`

3. Test:
	 - `curl -F "questions.txt=@question.txt" http://localhost:8000/api/`



