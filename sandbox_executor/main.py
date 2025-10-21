#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
import subprocess
import logging
import os
import pwd
from pathlib import Path
import io

import fitz  # PyMuPDF
from docx import Document as DocxDocument

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sandbox_executor")

app = FastAPI()

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_TEXT = 200_000
ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt', '.docx'}
ALLOWED_MIME_TYPES = {
    '.pdf': {'application/pdf', 'application/x-pdf'},
    '.md': {'text/markdown', 'text/plain'},
    '.txt': {'text/plain', 'text/markdown'},
    '.docx': {'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
}

class CodeExecutionRequest(BaseModel):
    language: str
    code: str
    timeout: int = 5

class CodeExecutionResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    error: str | None = None

def demote(user_uid, user_gid):
    def result():
        os.setgid(user_gid)
        os.setuid(user_uid)
    return result

@app.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(payload: CodeExecutionRequest):
    if payload.language != "python":
        raise HTTPException(status_code=400, detail="Only python is supported")

    logger.info(f"Executing code: {payload.code}")

    try:
        user_info = pwd.getpwnam("app")
        uid = user_info.pw_uid
        gid = user_info.pw_gid

        process = subprocess.run(
            ["python", "-c", payload.code],
            capture_output=True,
            text=True,
            timeout=payload.timeout,
            preexec_fn=demote(uid, gid)
        )
        return CodeExecutionResponse(
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.returncode,
        )
    except subprocess.TimeoutExpired:
        return CodeExecutionResponse(
            stdout="",
            stderr="Execution timed out",
            exit_code=1,
            error="TimeoutExpired",
        )
    except Exception as e:
        logger.error(f"Error executing code: {e}")
        return CodeExecutionResponse(
            stdout="",
            stderr=str(e),
            exit_code=1,
            error="ExecutionError",
        )


def _extract_pdf_text(data: bytes) -> str:
    with fitz.open(stream=data, filetype="pdf") as document:
        parts = [page.get_text("text") for page in document]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _extract_docx_text(data: bytes) -> str:
    document = DocxDocument(io.BytesIO(data))
    parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text and paragraph.text.strip()]
    return "\n".join(parts)


def _extract_plain_text(data: bytes) -> str:
    return data.decode('utf-8', errors='ignore')


def _is_allowed(extension: str, mime: str) -> bool:
    if extension not in ALLOWED_EXTENSIONS:
        return False
    if not mime:
        return True
    lowered = mime.lower()
    if lowered == 'application/octet-stream':
        return True
    allowed = ALLOWED_MIME_TYPES.get(extension)
    if not allowed:
        return False
    return lowered in allowed


@app.post('/analyze/document')
async def analyze_document(file: UploadFile = File(...)):
    filename = file.filename or 'document'
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported or unsafe file type")

    mime_type = (file.content_type or '').lower()
    if not _is_allowed(extension, mime_type):
        raise HTTPException(status_code=415, detail="Unsupported or unsafe file type")

    data = await file.read()
    await file.close()

    size = len(data)
    if size > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Payload Too Large")

    logger.info("[SANDBOX] Document received name=%s size=%s mime=%s", filename, size, mime_type or 'unknown')

    try:
        if extension == '.pdf':
            extracted = _extract_pdf_text(data)
        elif extension == '.docx':
            extracted = _extract_docx_text(data)
        else:
            extracted = _extract_plain_text(data)
    except Exception as exc:  # pragma: no cover - parsing failure
        logger.error("[SANDBOX] Failed to parse document %s: %s", filename, exc)
        raise HTTPException(status_code=500, detail="Failed to parse document") from exc

    truncated = extracted[:MAX_DOCUMENT_TEXT]
    if len(extracted) > MAX_DOCUMENT_TEXT:
        truncated += "\n\n[Truncated]"

    return {
        'text': truncated,
        'metadata': {
            'filename': filename,
            'mime_type': mime_type or 'application/octet-stream',
            'size': size,
        },
    }
