import os
import io
import json
import base64
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routes.api import router as api_router


def create_app() -> FastAPI:
    app = FastAPI(title="Data Analyst Agent API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "data-analyst-agent"}

    return app


app = create_app()


def dev():
    # Entrypoint for `uv run start` or `python -m app.main`
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)


if __name__ == "__main__":
    # This will run when the file is executed directly (e.g., python app/main.py)
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
