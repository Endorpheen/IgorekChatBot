#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import logging
import os
import pwd

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sandbox_executor")

app = FastAPI()

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