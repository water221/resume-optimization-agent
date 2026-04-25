from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.services.exporter import export_docx, export_md, export_pdf
from app.services.llm_client import llm_chat
from app.services.parser import read_upload
from app.services.resume_agent import (
    analyze_resume,
    get_resume_or_404,
    get_session,
    optimize_resume,
    trim_text,
)

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Resume Optimization Agent", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class AnalyzeRequest(BaseModel):
    resume_text: str = Field(..., min_length=20)
    jd_text: str = Field(..., min_length=20)
    source_filename: Optional[str] = ""


class OptimizeRequest(BaseModel):
    session_id: str
    user_confirmed: bool = True
    extra_instruction: Optional[str] = ""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.post("/api/parse-resume")
def parse_resume(file: UploadFile = File(...)):
    text = trim_text(read_upload(file))
    if not text:
        raise HTTPException(status_code=400, detail="无法从文件中解析出文本，请尝试粘贴简历文本。")
    return {"resume_text": text}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    resume_text = trim_text(req.resume_text)
    jd_text = trim_text(req.jd_text, max_chars=20000)
    return analyze_resume(
        resume_text=resume_text,
        jd_text=jd_text,
        source_filename=req.source_filename or "",
        llm_chat_func=llm_chat,
    )


@app.post("/api/optimize")
def optimize(req: OptimizeRequest):
    return optimize_resume(
        session_id=req.session_id,
        user_confirmed=req.user_confirmed,
        extra_instruction=req.extra_instruction or "",
        llm_chat_func=llm_chat,
    )


@app.get("/api/export/{session_id}.{fmt}")
def export_resume(session_id: str, fmt: str):
    content = get_resume_or_404(session_id)
    session = get_session(session_id)
    fmt = fmt.lower()

    if fmt == "md":
        path, filename, media_type = export_md(content, session, session_id, EXPORT_DIR)
        return FileResponse(path, filename=filename, media_type=media_type)

    if fmt == "docx":
        path, filename, media_type = export_docx(content, session, session_id, EXPORT_DIR)
        return FileResponse(path, filename=filename, media_type=media_type)

    if fmt == "pdf":
        path, filename, media_type = export_pdf(content, session, session_id, EXPORT_DIR)
        return FileResponse(path, filename=filename, media_type=media_type)

    raise HTTPException(status_code=400, detail="Unsupported format. Use md, docx, or pdf.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
def global_exception_handler(_, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(status_code=500, content={"detail": str(exc)})
