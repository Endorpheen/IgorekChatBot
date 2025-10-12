"""Image generation queue and Together API integration."""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import io
import logging
import os
import random
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Optional, TypedDict
from uuid import uuid4

import copy

import requests

ALLOWED_TOGETHER_MODEL = "black-forest-labs/FLUX.1-schnell-Free"


class ModelCapabilities(TypedDict):
    model: str
    steps_allowed: list[int]
    default_steps: int
    sizes_allowed: list[int]
    default_size: int


MODEL_CAPABILITIES: ModelCapabilities = {
    "model": ALLOWED_TOGETHER_MODEL,
    "steps_allowed": [1, 2, 3, 4],
    "default_steps": 4,
    "sizes_allowed": [512, 768, 1024],
    "default_size": 1024,
}

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Base exception for image generation failures."""

    def __init__(self, message: str, *, status_code: int = 500, error_code: str = "internal_error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(slots=True)
class ImageJobPayload:
    job_id: str
    prompt: str
    width: int
    height: int
    steps: int
    session_id: str
    together_key: str
    key_fingerprint: str
    created_at: datetime


@dataclass(slots=True)
class ImageJobRecord:
    job_id: str
    prompt: str
    provider: str
    width: int
    height: int
    steps: int
    status: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    result_path: Optional[str]


@dataclass(slots=True)
class JobStatus:
    status: str
    error_code: Optional[str]
    error_message: Optional[str]
    result_path: Optional[str]
    width: int
    height: int
    steps: int
    prompt: str
    provider: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]


class ImageGenerationManager:
    """Manages image generation jobs and queue processing."""

    def __init__(self) -> None:
        self.provider_name = os.getenv("TOGETHER_PROVIDER_NAME", "together-flux")
        self.capabilities = copy.deepcopy(MODEL_CAPABILITIES)
        self.together_model = self.capabilities["model"]
        self.together_url = os.getenv(
            "TOGETHER_GENERATE_URL",
            "https://api.together.xyz/v1/images/generations",
        )
        self.validate_url = os.getenv("TOGETHER_VALIDATE_URL", "https://api.together.xyz/v1/models")
        self.output_dir = Path(os.getenv("IMAGE_OUTPUT_DIR", Path.cwd() / "data" / "images")).resolve()
        self.db_path = Path(os.getenv("IMAGE_JOBS_DB", Path.cwd() / "data" / "image_jobs.sqlite")).resolve()
        self.queue_limit = max(1, int(os.getenv("IMAGE_QUEUE_LIMIT", "50")))
        self.timeout_seconds = max(10, int(os.getenv("IMAGE_TIMEOUT_SECONDS", "120")))
        self.max_retries = max(0, int(os.getenv("IMAGE_RETRY_MAX", "2")))
        self.rate_window = max(1, int(os.getenv("IMAGE_RATE_LIMIT_WINDOW", "5")))
        self.rate_max = max(1, int(os.getenv("IMAGE_RATE_LIMIT_MAX", "1")))
        self.active_limit = max(1, int(os.getenv("IMAGE_ACTIVE_LIMIT", "3")))
        self.allowed_sizes = self._build_allowed_sizes()
        self.allowed_steps = set(self.capabilities["steps_allowed"])
        self.max_prompt_chars = max(1, int(os.getenv("IMAGE_MAX_PROMPT_LEN", "800")))
        self.worker_count = max(1, int(os.getenv("IMAGE_WORKERS", "1")))

        self._queue: asyncio.Queue[ImageJobPayload] | None = None
        self._queue_lock: asyncio.Lock | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._active_by_key: Dict[str, int] = defaultdict(int)
        self._active_by_session: Dict[str, int] = defaultdict(int)
        self._rate_by_key: Dict[str, Deque[float]] = defaultdict(deque)
        self._rate_by_session: Dict[str, Deque[float]] = defaultdict(deque)
        self._db_lock = threading.Lock()

    async def startup(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self._queue = asyncio.Queue()
        self._queue_lock = asyncio.Lock()

        for _ in range(self.worker_count):
            task = asyncio.create_task(self._worker())
            self._workers.append(task)
        logger.info(
            "[IMAGE QUEUE] Initialised: workers=%s queue_limit=%s active_limit=%s", 
            self.worker_count,
            self.queue_limit,
            self.active_limit,
        )

    async def shutdown(self) -> None:
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._workers.clear()
        self._queue = None
        self._queue_lock = None
        logger.info("[IMAGE QUEUE] Shutdown complete")

    async def enqueue_job(
        self,
        *,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        session_id: str,
        together_key: str,
    ) -> str:
        if not self._queue or not self._queue_lock:
            raise ImageGenerationError("Очередь генерации недоступна", status_code=503, error_code="service_unavailable")

        normalised_prompt = prompt.strip()
        if not normalised_prompt:
            raise ImageGenerationError("Укажите подсказку для генерации", status_code=400, error_code="prompt_required")
        if len(normalised_prompt) > self.max_prompt_chars:
            raise ImageGenerationError("Подсказка слишком длинная", status_code=400, error_code="prompt_too_long")

        if (width, height) not in self.allowed_sizes:
            raise ImageGenerationError("Недопустимый размер изображения", status_code=400, error_code="size_not_allowed")
        if steps not in self.allowed_steps:
            raise ImageGenerationError(
                "steps must be between 1 and 4",
                status_code=400,
                error_code="steps_out_of_range",
            )

        session_id = session_id.strip() or "unknown-session"
        fingerprint = hashlib.sha256(together_key.encode("utf-8")).hexdigest()
        now = time.monotonic()

        async with self._queue_lock:
            if self._queue.qsize() >= self.queue_limit:
                raise ImageGenerationError("Очередь переполнена. Попробуйте позже.", status_code=503, error_code="queue_overflow")

            self._enforce_rate_limit(self._rate_by_key, fingerprint, now, subject="key")
            self._enforce_rate_limit(self._rate_by_session, session_id, now, subject="session")

            if self._active_by_key[fingerprint] >= self.active_limit:
                raise ImageGenerationError(
                    "Превышен лимит активных задач для этого ключа.",
                    status_code=429,
                    error_code="active_limit_key",
                )
            if self._active_by_session[session_id] >= self.active_limit:
                raise ImageGenerationError(
                    "Превышен лимит активных задач для вашей сессии.",
                    status_code=429,
                    error_code="active_limit_session",
                )

            job_id = uuid4().hex
            created_at = self._utcnow()
            payload = ImageJobPayload(
                job_id=job_id,
                prompt=normalised_prompt,
                width=width,
                height=height,
                steps=steps,
                session_id=session_id,
                together_key=together_key,
                key_fingerprint=fingerprint,
                created_at=created_at,
            )

            try:
                self._insert_job_record(payload)
            except sqlite3.DatabaseError as exc:
                logger.error("[IMAGE QUEUE] DB insert failed: %s", exc)
                raise ImageGenerationError("Не удалось создать задачу", status_code=500, error_code="db_error") from exc

            self._active_by_key[fingerprint] += 1
            self._active_by_session[session_id] += 1
            self._rate_by_key[fingerprint].append(now)
            self._rate_by_session[session_id].append(now)

            await self._queue.put(payload)

        logger.info("[IMAGE QUEUE] Job queued: %s session=%s", job_id, session_id)
        return job_id

    async def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        try:
            record = self._fetch_job_record(job_id)
        except sqlite3.DatabaseError as exc:
            logger.error("[IMAGE QUEUE] DB fetch failed: %s", exc)
            raise ImageGenerationError("Ошибка доступа к базе задач", status_code=500, error_code="db_error") from exc

        if not record:
            return None

        return JobStatus(
            status=record.status,
            error_code=record.error_code,
            error_message=record.error_message,
            result_path=record.result_path,
            width=record.width,
            height=record.height,
            steps=record.steps,
            prompt=record.prompt,
            provider=record.provider,
            session_id=record.session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_ms=record.duration_ms,
        )

    async def validate_key(self, together_key: str) -> None:
        def _request() -> requests.Response:
            return requests.get(
                self.validate_url,
                headers={"Authorization": f"Bearer {together_key}"},
                timeout=15,
            )

        try:
            response = await asyncio.to_thread(_request)
        except requests.Timeout as exc:
            raise ImageGenerationError("Проверка ключа превысила лимит времени", status_code=504, error_code="timeout") from exc
        except requests.RequestException as exc:
            raise ImageGenerationError("Не удалось связаться с Together", status_code=502, error_code="provider_unreachable") from exc

        status = response.status_code
        if status == 200:
            return
        if status in {401, 403}:
            raise ImageGenerationError("Ключ Together отклонён", status_code=status, error_code="invalid_key")
        if status == 429:
            raise ImageGenerationError("Превышен лимит Together", status_code=status, error_code="provider_rate_limited")
        if status >= 500:
            raise ImageGenerationError("Сервис Together недоступен", status_code=status, error_code="provider_unavailable")

        message = self._extract_error_message(response, default="Ключ не прошёл проверку")
        raise ImageGenerationError(message, status_code=status, error_code="provider_error")

    def ensure_session_access(self, job_id: str, session_id: str) -> bool:
        record = self._fetch_job_record(job_id)
        if not record:
            return False
        return record.session_id == session_id

    # Internal helpers -----------------------------------------------------

    async def _worker(self) -> None:
        while True:
            try:
                payload = await self._queue.get()  # type: ignore[arg-type]
            except asyncio.CancelledError:
                break

            try:
                await self._process_job(payload)
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("[IMAGE QUEUE] Unexpected worker error: %s", exc)
            finally:
                if self._queue:
                    self._queue.task_done()
                self._release_payload(payload)

    async def _process_job(self, payload: ImageJobPayload) -> None:
        start_perf = time.perf_counter()
        started_at = self._utcnow()
        self._update_job_record(
            payload.job_id,
            status="running",
            started_at=started_at,
            updated_at=started_at,
        )

        try:
            image_bytes = await self._call_together(payload)
        except ImageGenerationError as exc:
            logger.info("[IMAGE QUEUE] Job failed: %s code=%s", payload.job_id, exc.error_code)
            self._update_job_record(
                payload.job_id,
                status="error",
                error_code=exc.error_code,
                error_message=str(exc),
                updated_at=self._utcnow(),
                completed_at=self._utcnow(),
            )
            return
        except Exception as exc:  # pragma: no cover - unexpected errors
            logger.exception("[IMAGE QUEUE] Job crashed: %s", payload.job_id)
            self._update_job_record(
                payload.job_id,
                status="error",
                error_code="internal_error",
                error_message="Внутренняя ошибка генерации",
                updated_at=self._utcnow(),
                completed_at=self._utcnow(),
            )
            return

        try:
            output_path = self._store_image(payload.job_id, image_bytes)
        except OSError as exc:
            logger.error("[IMAGE QUEUE] Store failed: %s -> %s", payload.job_id, exc)
            self._update_job_record(
                payload.job_id,
                status="error",
                error_code="storage_error",
                error_message="Не удалось сохранить изображение",
                updated_at=self._utcnow(),
                completed_at=self._utcnow(),
            )
            return

        completed_at = self._utcnow()
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        self._update_job_record(
            payload.job_id,
            status="done",
            result_path=str(output_path),
            updated_at=completed_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        logger.info("[IMAGE QUEUE] Job done: %s", payload.job_id)

    async def _call_together(self, payload: ImageJobPayload) -> bytes:
        body: Dict[str, Any] = {
            "model": self.together_model,
            "prompt": payload.prompt,
            "width": payload.width,
            "height": payload.height,
            "steps": payload.steps,
            "n": 1,
            "response_format": "b64_json",
            "image_format": "webp",
        }
        headers = {
            "Authorization": f"Bearer {payload.together_key}",
            "Content-Type": "application/json",
        }

        attempt = 0
        while True:
            attempt += 1

            def _request() -> requests.Response:
                return requests.post(
                    self.together_url,
                    headers=headers,
                    json=body,
                    timeout=self.timeout_seconds,
                )

            try:
                response = await asyncio.to_thread(_request)
            except requests.Timeout:
                raise ImageGenerationError("Генерация превысила лимит времени", status_code=504, error_code="timeout")
            except requests.RequestException as exc:
                if attempt <= self.max_retries:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                raise ImageGenerationError("Не удалось связаться с Together", status_code=502, error_code="provider_unreachable") from exc

            status = response.status_code
            if status >= 500:
                if attempt <= self.max_retries:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                raise ImageGenerationError("Сервис Together недоступен", status_code=status, error_code="provider_unavailable")
            if status in {401, 403}:
                raise ImageGenerationError("Ключ Together отклонён", status_code=status, error_code="invalid_key")
            if status == 429:
                raise ImageGenerationError("Превышен лимит Together", status_code=status, error_code="provider_rate_limited")
            if status >= 400:
                message = self._extract_error_message(response, default="Провайдер отклонил запрос")
                lower = message.lower()
                if "unable to access model" in lower or "model" in lower and "access" in lower:
                    raise ImageGenerationError(
                        f"Модель недоступна. Разрешена: {ALLOWED_TOGETHER_MODEL}",
                        status_code=400,
                        error_code="model_not_allowed",
                    )
                raise ImageGenerationError(message, status_code=status, error_code="provider_error")

            try:
                payload_json = response.json()
            except ValueError as exc:
                raise ImageGenerationError("Неверный ответ Together", status_code=502, error_code="invalid_response") from exc

            try:
                data = payload_json.get("data")
                if not isinstance(data, list) or not data:
                    raise ValueError("data")
                first = data[0]
                b64_value = first.get("b64_json")
                if not isinstance(b64_value, str):
                    raise ValueError("b64_json")
                return base64.b64decode(b64_value)
            except (ValueError, TypeError, binascii.Error) as exc:  # type: ignore[name-defined]
                raise ImageGenerationError("Ответ Together не содержит изображение", status_code=502, error_code="invalid_response") from exc

    def _store_image(self, job_id: str, image_bytes: bytes) -> Path:
        if not self._looks_like_webp(image_bytes):
            try:
                from PIL import Image  # type: ignore

                with Image.open(io.BytesIO(image_bytes)) as img:
                    buffer = io.BytesIO()
                    img.save(buffer, format="WEBP", quality=88, method=6)
                    image_bytes = buffer.getvalue()
            except ImportError:
                logger.warning("[IMAGE QUEUE] Pillow не установлен, сохраняю исходный формат для job %s", job_id)
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("[IMAGE QUEUE] Не удалось конвертировать в WEBP: %s", exc)

        file_path = self.output_dir / f"{job_id}.webp"
        with open(file_path, "wb") as file_obj:
            file_obj.write(image_bytes)
        return file_path

    def _release_payload(self, payload: ImageJobPayload) -> None:
        self._active_by_key[payload.key_fingerprint] = max(0, self._active_by_key[payload.key_fingerprint] - 1)
        self._active_by_session[payload.session_id] = max(0, self._active_by_session[payload.session_id] - 1)
        payload.together_key = ""

    def _init_db(self) -> None:
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS image_jobs (
                        job_id TEXT PRIMARY KEY,
                        prompt TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        width INTEGER NOT NULL,
                        height INTEGER NOT NULL,
                        steps INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        duration_ms INTEGER,
                        error_code TEXT,
                        error_message TEXT,
                        result_path TEXT
                    )
                    """
                )
            finally:
                conn.close()

    def _insert_job_record(self, payload: ImageJobPayload) -> None:
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.execute(
                    """
                    INSERT INTO image_jobs (
                        job_id, prompt, provider, width, height, steps, status, session_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.job_id,
                        payload.prompt,
                        self.provider_name,
                        payload.width,
                        payload.height,
                        payload.steps,
                        "queued",
                        payload.session_id,
                        self._isoformat(payload.created_at),
                        self._isoformat(payload.created_at),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def _update_job_record(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        result_path: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        fields: list[str] = []
        params: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if result_path is not None:
            fields.append("result_path = ?")
            params.append(result_path)
        if error_code is not None:
            fields.append("error_code = ?")
            params.append(error_code)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if started_at is not None:
            fields.append("started_at = ?")
            params.append(self._isoformat(started_at))
        if completed_at is not None:
            fields.append("completed_at = ?")
            params.append(self._isoformat(completed_at))
        if updated_at is not None:
            fields.append("updated_at = ?")
            params.append(self._isoformat(updated_at))
        if duration_ms is not None:
            fields.append("duration_ms = ?")
            params.append(duration_ms)

        if not fields:
            return

        fields_clause = ", ".join(fields)
        params.append(job_id)

        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.execute(f"UPDATE image_jobs SET {fields_clause} WHERE job_id = ?", tuple(params))
                conn.commit()
            finally:
                conn.close()

    def _fetch_job_record(self, job_id: str) -> Optional[ImageJobRecord]:
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                row = conn.execute(
                    """
                    SELECT job_id, prompt, provider, width, height, steps, status, session_id,
                           created_at, updated_at, started_at, completed_at, duration_ms,
                           error_code, error_message, result_path
                    FROM image_jobs
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
            finally:
                conn.close()

        if not row:
            return None

        (
            job_id,
            prompt,
            provider,
            width,
            height,
            steps,
            status,
            session_id,
            created_at,
            updated_at,
            started_at,
            completed_at,
            duration_ms,
            error_code,
            error_message,
            result_path,
        ) = row

        return ImageJobRecord(
            job_id=job_id,
            prompt=prompt,
            provider=provider,
            width=int(width),
            height=int(height),
            steps=int(steps),
            status=status,
            session_id=session_id,
            created_at=self._parse_dt(created_at),
            updated_at=self._parse_dt(updated_at),
            started_at=self._parse_dt(started_at) if started_at else None,
            completed_at=self._parse_dt(completed_at) if completed_at else None,
            duration_ms=int(duration_ms) if duration_ms is not None else None,
            error_code=error_code,
            error_message=error_message,
            result_path=result_path,
        )

    def _enforce_rate_limit(
        self,
        bucket: Dict[str, Deque[float]],
        key: str,
        now: float,
        *,
        subject: str,
    ) -> None:
        history = bucket[key]
        window_start = now - self.rate_window
        while history and history[0] < window_start:
            history.popleft()
        if len(history) >= self.rate_max:
            if subject == "key":
                raise ImageGenerationError(
                    "Слишком частые запросы с этим ключом. Подождите пару секунд.",
                    status_code=429,
                    error_code="rate_limit_key",
                )
            raise ImageGenerationError(
                "Слишком частые запросы из вашей сессии. Подождите немного.",
                status_code=429,
                error_code="rate_limit_session",
            )

    def _retry_delay(self, attempt: int) -> float:
        base = 1.5 ** attempt
        jitter = random.uniform(0.2, 0.6)
        return min(10.0, base + jitter)

    def _extract_error_message(self, response: requests.Response, *, default: str) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    message = error.get("message")
                    if isinstance(message, str) and message.strip():
                        return message.strip()
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        except ValueError:
            pass
        return default

    @staticmethod
    def _looks_like_webp(image_bytes: bytes) -> bool:
        return len(image_bytes) > 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP"

    @staticmethod
    def _isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _parse_dt(raw: str) -> datetime:
        return datetime.fromisoformat(raw)

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _build_allowed_sizes(self) -> set[tuple[int, int]]:
        sizes: set[tuple[int, int]] = set()
        for size in self.capabilities["sizes_allowed"]:
            sizes.add((size, size))
        if not sizes:
            default_size = self.capabilities["default_size"]
            sizes.add((default_size, default_size))
        return sizes


image_manager = ImageGenerationManager()


def get_allowed_model() -> str:
    return ALLOWED_TOGETHER_MODEL


def get_model_capabilities() -> ModelCapabilities:
    return copy.deepcopy(MODEL_CAPABILITIES)
