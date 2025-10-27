"""Управление мультипровайдерной генерацией изображений."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple
from uuid import uuid4

import copy

from .providers import PROVIDER_REGISTRY, build_adapter
from .providers.base import (
    DEFAULT_CFG,
    DEFAULT_SEED_RANGE,
    DEFAULT_SIZE_PRESETS,
    DEFAULT_STEPS,
    GenerateResult,
    ImageProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderModelSpec,
)

logger = logging.getLogger(__name__)


class ImageGenerationError(Exception):
    """Базовое исключение для ошибок генерации."""

    def __init__(self, message: str, *, status_code: int = 500, error_code: str = "internal_error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


@dataclass(slots=True)
class ImageJobPayload:
    job_id: str
    prompt: str
    provider_id: str
    model_id: str
    width: int
    height: int
    steps: int
    cfg: float | None
    seed: int | None
    mode: str | None
    params: Dict[str, Any]
    session_id: str
    api_key: str
    key_fingerprint: str
    created_at: datetime


@dataclass(slots=True)
class ImageJobRecord:
    job_id: str
    prompt: str
    provider: str
    model: str
    width: int
    height: int
    steps: int
    cfg: float | None
    seed: int | None
    mode: str | None
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
    provider: str
    model: str
    prompt: str
    width: int
    height: int
    steps: int
    cfg: float | None
    seed: int | None
    mode: str | None
    session_id: str
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]


@dataclass(slots=True)
class ModelCacheEntry:
    models: List[ProviderModelSpec]
    fetched_at: float


@dataclass(slots=True)
class BreakerState:
    fail_count: int = 0
    cooldown_until: float = 0.0


class ImageGenerationManager:
    """Менеджер очереди генерации изображений."""

    def __init__(self) -> None:
        self.registry = copy.deepcopy(PROVIDER_REGISTRY)
        self.output_dir = Path(os.getenv("IMAGE_OUTPUT_DIR", Path.cwd() / "data" / "images")).resolve()
        self.db_path = Path(os.getenv("IMAGE_JOBS_DB", Path.cwd() / "data" / "image_jobs.sqlite")).resolve()
        self.queue_limit = max(1, int(os.getenv("IMAGE_QUEUE_LIMIT", "50")))
        self.timeout_seconds = max(10, int(os.getenv("IMAGE_TIMEOUT_SECONDS", "120")))
        self.max_retries = max(0, int(os.getenv("IMAGE_RETRY_MAX", "2")))
        self.rate_window = max(1, int(os.getenv("IMAGE_RATE_LIMIT_WINDOW", "5")))
        self.rate_max = max(1, int(os.getenv("IMAGE_RATE_LIMIT_MAX", "1")))
        self.active_limit = max(1, int(os.getenv("IMAGE_ACTIVE_LIMIT", "3")))
        self.worker_count = max(1, int(os.getenv("IMAGE_WORKERS", "1")))
        self.max_prompt_chars = max(1, int(os.getenv("IMAGE_MAX_PROMPT_LEN", "800")))
        self.model_cache_ttl = max(60, int(os.getenv("IMAGE_MODEL_CACHE_TTL", str(60 * 20))))
        self.breaker_threshold = max(1, int(os.getenv("IMAGE_BREAKER_THRESHOLD", "3")))
        self.breaker_cooldown = max(1, int(os.getenv("IMAGE_BREAKER_COOLDOWN", "60")))
        self.cleanup_interval = max(0, int(os.getenv("IMAGE_CLEANUP_INTERVAL_SECONDS", str(24 * 3600))))
        self.job_ttl_days = max(0, int(os.getenv("IMAGE_JOB_TTL_DAYS", "7")))
        self.result_ttl_days = max(0, int(os.getenv("IMAGE_CLEANUP_TTL_DAYS", "30")))
        self.max_storage_bytes = max(
            0,
            int(float(os.getenv("IMAGE_MAX_STORAGE_MB", "0")) * 1024 * 1024),
        )
        self.orphan_grace_seconds = max(0, int(os.getenv("IMAGE_ORPHAN_GRACE_SECONDS", "300")))
        self.vacuum_on_cleanup = os.getenv("IMAGE_CLEANUP_VACUUM", "true").lower() not in {"false", "0", "no"}

        self._queue: asyncio.Queue[ImageJobPayload] | None = None
        self._queue_lock: asyncio.Lock | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._active_by_key: Dict[Tuple[str, str], int] = defaultdict(int)
        self._active_by_session: Dict[str, int] = defaultdict(int)
        self._rate_by_key: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._rate_by_session: Dict[str, Deque[float]] = defaultdict(deque)
        self._breaker: Dict[Tuple[str, str], BreakerState] = defaultdict(BreakerState)
        self._model_cache: Dict[Tuple[str, str], ModelCacheEntry] = {}
        self._adapters: Dict[str, ImageProviderAdapter] = {}
        self._db_lock = threading.Lock()
        self._cleanup_task: Optional[asyncio.Task[None]] = None

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
        try:
            await self._run_cleanup_once(initial=True)
        except Exception:  # pragma: no cover - защита от неожиданных сбоев
            logger.exception("[IMAGE CLEANUP] Initial cleanup failed")
        if self.cleanup_interval > 0:
            self._cleanup_task = asyncio.create_task(self._cleanup_worker())

    async def shutdown(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
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
        provider_id: str,
        model_id: str,
        prompt: str,
        params: Dict[str, Any],
        session_id: str,
        api_key: str,
    ) -> str:
        if not self._queue or not self._queue_lock:
            raise ImageGenerationError("Очередь генерации недоступна", status_code=503, error_code="service_unavailable")

        provider_id = provider_id.lower().strip()
        if provider_id not in self.registry:
            raise ImageGenerationError("Указан неподдерживаемый провайдер", status_code=400, error_code="provider_unknown")
        session_id = session_id.strip() or "unknown-session"
        normalised_prompt = prompt.strip()
        if not normalised_prompt:
            raise ImageGenerationError("Укажите подсказку для генерации", status_code=400, error_code="prompt_required")
        if len(normalised_prompt) > self.max_prompt_chars:
            raise ImageGenerationError("Подсказка слишком длинная", status_code=400, error_code="prompt_too_long")

        key_fingerprint = self._fingerprint(api_key)
        breaker_key = (provider_id, key_fingerprint)
        now = time.monotonic()
        breaker_state = self._breaker[breaker_key]
        if breaker_state.cooldown_until > now:
            cooldown = int(breaker_state.cooldown_until - now)
            raise ImageGenerationError(
                f"Провайдер временно охлаждён после ошибок. Подождите {cooldown} с.",
                status_code=429,
                error_code="provider_cooldown",
            )

        adapter = self._get_adapter(provider_id)
        model_spec = await self._ensure_model_spec(provider_id, model_id, api_key)

        try:
            validated = adapter.validate_params(model_id, params, model_spec=model_spec)
        except ProviderError as exc:
            raise self._map_provider_error(exc) from exc

        validated.setdefault("model", model_id)
        width = int(validated.get("width", DEFAULT_SIZE_PRESETS[0][0]))
        height = int(validated.get("height", DEFAULT_SIZE_PRESETS[0][1]))
        steps = int(validated.get("steps", DEFAULT_STEPS))
        cfg = validated.get("cfg")
        seed = validated.get("seed")
        mode = validated.get("mode")

        async with self._queue_lock:
            if self._queue.qsize() >= self.queue_limit:
                raise ImageGenerationError("Очередь переполнена. Попробуйте позже.", status_code=503, error_code="queue_overflow")

            self._enforce_rate_limit(self._rate_by_key, breaker_key, now, subject="key")
            self._enforce_rate_limit(self._rate_by_session, session_id, now, subject="session")

            if self._active_by_key[breaker_key] >= self.active_limit:
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
                provider_id=provider_id,
                model_id=model_id,
                width=width,
                height=height,
                steps=steps,
                cfg=float(cfg) if cfg is not None else None,
                seed=int(seed) if isinstance(seed, int) else None,
                mode=str(mode) if mode else None,
                params=validated,
                session_id=session_id,
                api_key=api_key,
                key_fingerprint=key_fingerprint,
                created_at=created_at,
            )

            try:
                self._insert_job_record(payload)
            except sqlite3.DatabaseError as exc:
                logger.error("[IMAGE QUEUE] DB insert failed: %s", exc)
                raise ImageGenerationError("Не удалось создать задачу", status_code=500, error_code="db_error") from exc

            self._active_by_key[breaker_key] += 1
            self._active_by_session[session_id] += 1
            self._rate_by_key[breaker_key].append(now)
            self._rate_by_session[session_id].append(now)

            await self._queue.put(payload)

        logger.info(
            "[IMAGE QUEUE] Job queued: %s provider=%s model=%s session=%s",
            job_id,
            provider_id,
            model_id,
            session_id,
        )
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
            provider=record.provider,
            model=record.model,
            prompt=record.prompt,
            width=record.width,
            height=record.height,
            steps=record.steps,
            cfg=record.cfg,
            seed=record.seed,
            mode=record.mode,
            session_id=record.session_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_ms=record.duration_ms,
        )

    async def validate_key(self, provider_id: str, api_key: str) -> None:
        provider_id = provider_id.lower().strip()
        if provider_id not in self.registry:
            raise ImageGenerationError("Неизвестный провайдер", status_code=400, error_code="provider_unknown")
        adapter = self._get_adapter(provider_id)
        try:
            adapter.list_models(api_key, force=True)
        except ProviderError as exc:
            raise self._map_provider_error(exc) from exc

    async def get_provider_models(
        self,
        provider_id: str,
        api_key: str,
        *,
        force: bool = False,
    ) -> List[ProviderModelSpec]:
        provider_id = provider_id.lower().strip()
        if provider_id not in self.registry:
            raise ImageGenerationError("Неизвестный провайдер", status_code=400, error_code="provider_unknown")
        return await self._load_models(provider_id, api_key, force=force)

    async def search_provider_models(
        self,
        provider_id: str,
        api_key: str,
        query: str,
        *,
        limit: int = 50,
    ) -> List[ProviderModelSpec]:
        provider_id = provider_id.lower().strip()
        if provider_id not in self.registry:
            raise ImageGenerationError("Неизвестный провайдер", status_code=400, error_code="provider_unknown")
        search_query = query.strip()
        if not search_query:
            raise ImageGenerationError("Поисковый запрос не может быть пустым", status_code=400, error_code="query_empty")
        if provider_id != "replicate":
            raise ImageGenerationError("Поиск поддерживается только для Replicate", status_code=400, error_code="search_not_supported")

        adapter = self._get_adapter(provider_id)
        try:
            models = adapter.search_models(search_query, api_key, limit=limit)
        except ProviderError as exc:
            raise self._map_provider_error(exc) from exc

        return copy.deepcopy(models)

    def list_providers(self) -> List[Dict[str, Any]]:
        providers = []
        for entry in self.registry.values():
            providers.append(
                {
                    "id": entry["id"],
                    "label": entry.get("label", entry["id"]),
                    "enabled": entry.get("enabled", True),
                    "description": entry.get("description"),
                    "recommended_models": list(entry.get("recommended_models", [])),
                }
            )
        return providers

    async def _cleanup_worker(self) -> None:
        interval = max(self.cleanup_interval, 300)
        while True:
            try:
                await asyncio.sleep(interval)
                await self._run_cleanup_once()
            except asyncio.CancelledError:
                break
            except Exception:  # pragma: no cover - защита от неожиданных сбоев
                logger.exception("[IMAGE CLEANUP] Scheduled cleanup failed")

    async def _run_cleanup_once(self, *, initial: bool = False) -> None:
        await asyncio.to_thread(self._perform_cleanup, initial)

    def _perform_cleanup(self, initial: bool) -> None:
        job_stats = self._cleanup_jobs()
        file_stats = self._cleanup_result_files()
        total_jobs_removed = (
            job_stats["removed_by_age"] + job_stats["removed_missing"] + job_stats["removed_stuck"]
        )
        freed_mb = file_stats["removed_bytes"] / (1024 * 1024) if file_stats["removed_bytes"] else 0.0
        total_mb = file_stats["total_bytes"] / (1024 * 1024) if file_stats["total_bytes"] else 0.0
        logger.info(
            "[IMAGE CLEANUP] initial=%s jobs_removed=%s (age=%s, missing=%s, queued=%s) "
            "vacuum=%s files_removed=%s (orphan=%s, ttl=%s, quota=%s) freed_mb=%.2f total_mb=%.2f",
            initial,
            total_jobs_removed,
            job_stats["removed_by_age"],
            job_stats["removed_missing"],
            job_stats["removed_stuck"],
            job_stats["vacuum"],
            file_stats["removed"],
            file_stats["reasons"]["orphan"],
            file_stats["reasons"]["ttl"],
            file_stats["reasons"]["quota"],
            freed_mb,
            total_mb,
        )

    def _cleanup_jobs(self) -> Dict[str, int]:
        stats = {
            "removed_by_age": 0,
            "removed_missing": 0,
            "removed_stuck": 0,
            "vacuum": False,
        }
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.row_factory = sqlite3.Row
                if self.job_ttl_days > 0:
                    cutoff = self._isoformat(self._utcnow() - timedelta(days=self.job_ttl_days))
                    cursor = conn.execute(
                        "DELETE FROM image_jobs WHERE status IN ('done','error') AND updated_at < ?",
                        (cutoff,),
                    )
                    stats["removed_by_age"] += max(cursor.rowcount or 0, 0)
                    cursor = conn.execute(
                        "DELETE FROM image_jobs WHERE status = 'queued' AND updated_at < ?",
                        (cutoff,),
                    )
                    stats["removed_stuck"] += max(cursor.rowcount or 0, 0)

                rows = conn.execute(
                    "SELECT job_id, result_path FROM image_jobs WHERE status IN ('done','error')"
                ).fetchall()
                missing_ids: list[tuple[str]] = []
                for row in rows:
                    job_id = row["job_id"]
                    result_path = row["result_path"]
                    if not result_path:
                        missing_ids.append((job_id,))
                        continue
                    if not Path(result_path).is_file():
                        missing_ids.append((job_id,))
                if missing_ids:
                    conn.executemany("DELETE FROM image_jobs WHERE job_id = ?", missing_ids)
                    stats["removed_missing"] += len(missing_ids)

                conn.commit()
                total_removed = stats["removed_by_age"] + stats["removed_missing"] + stats["removed_stuck"]
                if total_removed > 0 and self.vacuum_on_cleanup:
                    conn.execute("VACUUM")
                    stats["vacuum"] = True
            finally:
                conn.close()
        return stats

    def _cleanup_result_files(self) -> Dict[str, Any]:
        stats = {
            "removed": 0,
            "removed_bytes": 0,
            "total_bytes": 0,
            "reasons": {"orphan": 0, "ttl": 0, "quota": 0},
        }
        if not self.output_dir.exists():
            return stats

        now = time.time()
        entries: list[dict[str, Any]] = []
        for path in self.output_dir.glob("**/*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            resolved = path.resolve()
            entries.append({"path": path, "resolved": resolved, "size": stat.st_size, "mtime": stat.st_mtime})
            stats["total_bytes"] += stat.st_size

        rows: list[sqlite3.Row] = []
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT job_id, status, result_path FROM image_jobs "
                    "WHERE result_path IS NOT NULL AND result_path != ''"
                ).fetchall()
            finally:
                conn.close()

        referenced: Dict[Path, Dict[str, Any]] = {}
        for row in rows:
            path = Path(row["result_path"]).resolve()
            referenced[path] = {"job_id": row["job_id"], "status": row["status"]}

        removed_paths: set[Path] = set()
        ttl_seconds = self.result_ttl_days * 24 * 3600 if self.result_ttl_days > 0 else 0
        orphan_grace = self.orphan_grace_seconds

        def _remove_entry(entry: dict[str, Any], reason: str) -> None:
            path: Path = entry["path"]
            resolved_path: Path = entry["resolved"]
            if resolved_path in removed_paths:
                return
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("[IMAGE CLEANUP] Failed to delete %s: %s", path, exc)
                return
            removed_paths.add(resolved_path)
            stats["removed"] += 1
            stats["removed_bytes"] += entry["size"]
            stats["total_bytes"] -= entry["size"]
            stats["reasons"][reason] += 1
            if stats["total_bytes"] < 0:
                stats["total_bytes"] = 0

        # Удаляем осиротевшие файлы, которых нет в базе (за исключением совсем свежих)
        if orphan_grace > 0:
            orphan_cutoff = now - orphan_grace
        else:
            orphan_cutoff = None
        for entry in entries:
            resolved_path = entry["resolved"]
            if resolved_path in referenced:
                continue
            if orphan_cutoff is not None and entry["mtime"] > orphan_cutoff:
                continue
            _remove_entry(entry, "orphan")

        # Удаляем старые файлы (TTL) только для завершённых задач
        if ttl_seconds > 0:
            ttl_cutoff = now - ttl_seconds
            for entry in entries:
                if entry["resolved"] in removed_paths:
                    continue
                if entry["mtime"] >= ttl_cutoff:
                    continue
                ref = referenced.get(entry["resolved"])
                if not ref or ref["status"] not in {"done", "error"}:
                    continue
                _remove_entry(entry, "ttl")

        # Контроль общего размера
        if self.max_storage_bytes > 0 and stats["total_bytes"] > self.max_storage_bytes:
            candidates = sorted(
                (entry for entry in entries if entry["resolved"] not in removed_paths),
                key=lambda item: item["mtime"],
            )
            for entry in candidates:
                if stats["total_bytes"] <= self.max_storage_bytes:
                    break
                ref = referenced.get(entry["resolved"])
                if ref and ref["status"] not in {"done", "error"}:
                    continue
                _remove_entry(entry, "quota")
            if stats["total_bytes"] > self.max_storage_bytes:
                logger.warning(
                    "[IMAGE CLEANUP] Unable to reduce image storage below %s bytes (current=%s)",
                    self.max_storage_bytes,
                    stats["total_bytes"],
                )

        return stats

    # Внутренние методы --------------------------------------------------

    def _get_adapter(self, provider_id: str) -> ImageProviderAdapter:
        try:
            return self._adapters[provider_id]
        except KeyError:
            adapter = build_adapter(provider_id)
            self._adapters[provider_id] = adapter
            return adapter

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
        breaker_key = (payload.provider_id, payload.key_fingerprint)
        start_perf = time.perf_counter()
        started_at = self._utcnow()
        self._update_job_record(
            payload.job_id,
            status="running",
            started_at=started_at,
            updated_at=started_at,
        )

        adapter = self._get_adapter(payload.provider_id)
        attempt = 0
        last_error: Optional[ProviderError] = None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                result = await adapter.generate(payload.prompt, payload.params, payload.api_key)
                self._reset_breaker(breaker_key)
                await self._store_success(payload, result, start_perf)
                return
            except ProviderError as exc:
                last_error = exc
                should_retry = exc.code in {
                    ProviderErrorCode.PROVIDER_ERROR,
                    ProviderErrorCode.TIMEOUT,
                }
                if exc.code == ProviderErrorCode.RATE_LIMIT and exc.retry_after:
                    await asyncio.sleep(min(float(exc.retry_after), 5.0))
                    should_retry = True
                if not should_retry or attempt > self.max_retries:
                    break
                await asyncio.sleep(self._retry_delay(attempt))
            except Exception as exc:  # pragma: no cover - unexpected
                logger.exception("[IMAGE QUEUE] Job crashed: %s", payload.job_id)
                last_error = ProviderError(ProviderErrorCode.INTERNAL, "Неожиданная ошибка генерации")
                break

        self._register_failure(breaker_key, last_error)
        error_code, error_message = self._provider_error_to_payload(last_error)
        logger.info(
            "[IMAGE QUEUE] Job failed: %s provider=%s code=%s",
            payload.job_id,
            payload.provider_id,
            error_code,
        )
        self._update_job_record(
            payload.job_id,
            status="error",
            error_code=error_code,
            error_message=error_message,
            updated_at=self._utcnow(),
            completed_at=self._utcnow(),
        )

    async def _store_success(self, payload: ImageJobPayload, result: GenerateResult, start_perf: float) -> None:
        if result.image_bytes is None and result.image_url:
            logger.error("[IMAGE QUEUE] Provider returned URL-only result, unsupported: %s", payload.provider_id)
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Провайдер вернул неподдерживаемый результат")

        image_bytes = result.image_bytes or b""
        if not self._looks_like_webp(image_bytes):
            # Попытаемся завернуть в WEBP через pillow.
            try:
                from PIL import Image  # type: ignore

                import io

                with Image.open(io.BytesIO(image_bytes)) as img:
                    buffer = io.BytesIO()
                    img.save(buffer, format="WEBP", quality=88, method=6)
                    image_bytes = buffer.getvalue()
            except ImportError:
                logger.warning("[IMAGE QUEUE] Pillow не установлен, сохраняю исходный формат для job %s", payload.job_id)
            except Exception as exc:  # pragma: no cover
                logger.warning("[IMAGE QUEUE] Не удалось конвертировать в WEBP: %s", exc)

        file_path = self.output_dir / f"{payload.job_id}.webp"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as file_obj:
            file_obj.write(image_bytes)

        completed_at = self._utcnow()
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        self._update_job_record(
            payload.job_id,
            status="done",
            result_path=str(file_path),
            updated_at=completed_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        logger.info(
            "[IMAGE QUEUE] Job done: %s provider=%s model=%s duration_ms=%s",
            payload.job_id,
            payload.provider_id,
            payload.model_id,
            duration_ms,
        )

    async def _ensure_model_spec(self, provider_id: str, model_id: str, api_key: str) -> ProviderModelSpec:
        models = await self._load_models(provider_id, api_key, force=False)
        for spec in models:
            if spec.get("id") == model_id:
                return spec
        # Попробуем принудительно обновить
        models = await self._load_models(provider_id, api_key, force=True)
        for spec in models:
            if spec.get("id") == model_id:
                return spec
        raise ImageGenerationError("Модель не найдена у провайдера", status_code=400, error_code="model_unknown")

    async def _load_models(self, provider_id: str, api_key: str, *, force: bool) -> List[ProviderModelSpec]:
        key_fingerprint = self._fingerprint(api_key)
        cache_key = (provider_id, key_fingerprint)
        now = time.monotonic()
        cache_entry = self._model_cache.get(cache_key)
        if cache_entry and not force and now - cache_entry.fetched_at < self.model_cache_ttl:
            return copy.deepcopy(cache_entry.models)

        adapter = self._get_adapter(provider_id)
        try:
            models = adapter.list_models(api_key, force=force)
        except ProviderError as exc:
            raise self._map_provider_error(exc) from exc

        featured_models: List[ProviderModelSpec] = []
        if provider_id == "replicate" and hasattr(adapter, "get_featured_models"):
            try:
                featured_models = adapter.get_featured_models(api_key)
            except ProviderError as exc:
                logger.warning("[IMAGE QUEUE] Не удалось загрузить избранные модели Replicate: %s", exc)
            except Exception as exc:  # pragma: no cover - safety net
                logger.warning("[IMAGE QUEUE] Ошибка при получении избранных моделей Replicate: %s", exc)

        if featured_models:
            combined: Dict[str, ProviderModelSpec] = {}
            featured_order: List[str] = []

            for spec in featured_models:
                spec_copy = copy.deepcopy(spec)
                spec_id = spec_copy.get("id")
                if not spec_id:
                    continue
                spec_copy["recommended"] = True
                combined[spec_id] = spec_copy
                featured_order.append(spec_id)

            for spec in models:
                spec_id = spec.get("id")
                if not spec_id:
                    continue
                if spec_id in combined:
                    merged = copy.deepcopy(spec)
                    merged["recommended"] = True
                    combined[spec_id] = merged
                else:
                    combined[spec_id] = spec

            ordered_models = [combined[item_id] for item_id in featured_order if item_id in combined]
            ordered_models.extend(spec for item_id, spec in combined.items() if item_id not in featured_order)
            models = ordered_models

        self._model_cache[cache_key] = ModelCacheEntry(models=models, fetched_at=now)
        return copy.deepcopy(models)

    def _register_failure(self, breaker_key: Tuple[str, str], exc: Optional[ProviderError]) -> None:
        state = self._breaker[breaker_key]
        state.fail_count += 1
        if state.fail_count >= self.breaker_threshold:
            state.cooldown_until = time.monotonic() + self.breaker_cooldown
        if exc:
            logger.warning(
                "[IMAGE QUEUE] provider=%s key=%s failure=%s count=%s",
                breaker_key[0],
                breaker_key[1][:8],
                exc.code.value,
                state.fail_count,
            )

    def _reset_breaker(self, breaker_key: Tuple[str, str]) -> None:
        state = self._breaker[breaker_key]
        state.fail_count = 0
        state.cooldown_until = 0.0

    def _provider_error_to_payload(self, exc: Optional[ProviderError]) -> Tuple[str, str]:
        if not exc:
            return "provider_error", "Неизвестная ошибка провайдера"
        mapping = {
            ProviderErrorCode.UNAUTHORIZED: ("unauthorized", "Ключ отклонён провайдером"),
            ProviderErrorCode.RATE_LIMIT: ("rate_limit", "Провайдер ограничил частоту запросов"),
            ProviderErrorCode.BAD_REQUEST: ("bad_request", str(exc)),
            ProviderErrorCode.PROVIDER_ERROR: ("provider_error", "Провайдер недоступен"),
            ProviderErrorCode.TIMEOUT: ("timeout", "Истек таймаут генерации"),
            ProviderErrorCode.INTERNAL: ("internal_error", "Внутренняя ошибка генерации"),
        }
        return mapping.get(exc.code, ("provider_error", str(exc)))

    def _map_provider_error(self, exc: ProviderError) -> ImageGenerationError:
        mapping = {
            ProviderErrorCode.UNAUTHORIZED: 401,
            ProviderErrorCode.RATE_LIMIT: 429,
            ProviderErrorCode.BAD_REQUEST: 400,
            ProviderErrorCode.PROVIDER_ERROR: 502,
            ProviderErrorCode.TIMEOUT: 504,
            ProviderErrorCode.INTERNAL: 500,
        }
        return ImageGenerationError(str(exc), status_code=mapping[exc.code], error_code=exc.code.value.lower())

    def _release_payload(self, payload: ImageJobPayload) -> None:
        breaker_key = (payload.provider_id, payload.key_fingerprint)
        self._active_by_key[breaker_key] = max(0, self._active_by_key[breaker_key] - 1)
        self._active_by_session[payload.session_id] = max(0, self._active_by_session[payload.session_id] - 1)
        payload.api_key = ""

    # Работа с базой -----------------------------------------------------

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
                        model TEXT NOT NULL,
                        width INTEGER NOT NULL,
                        height INTEGER NOT NULL,
                        steps INTEGER NOT NULL,
                        cfg REAL,
                        seed INTEGER,
                        mode TEXT,
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
                existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(image_jobs)")}
                for column_def in (
                    ("provider", "TEXT"),
                    ("model", "TEXT"),
                    ("cfg", "REAL"),
                    ("seed", "INTEGER"),
                    ("mode", "TEXT"),
                ):
                    if column_def[0] not in existing_columns:
                        conn.execute(f"ALTER TABLE image_jobs ADD COLUMN {column_def[0]} {column_def[1]}")
                conn.commit()
            finally:
                conn.close()

    def _insert_job_record(self, payload: ImageJobPayload) -> None:
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.execute(
                    """
                    INSERT INTO image_jobs (
                        job_id, prompt, provider, model, width, height, steps, cfg, seed, mode,
                        status, session_id, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.job_id,
                        payload.prompt,
                        payload.provider_id,
                        payload.model_id,
                        payload.width,
                        payload.height,
                        payload.steps,
                        payload.cfg,
                        payload.seed,
                        payload.mode,
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
        updated_at: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        fields = []
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
        if updated_at is None:
            updated_at = self._utcnow()
        fields.append("updated_at = ?")
        params.append(self._isoformat(updated_at))
        if started_at is not None:
            fields.append("started_at = ?")
            params.append(self._isoformat(started_at))
        if completed_at is not None:
            fields.append("completed_at = ?")
            params.append(self._isoformat(completed_at))
        if duration_ms is not None:
            fields.append("duration_ms = ?")
            params.append(duration_ms)

        if not fields:
            return

        params.append(job_id)
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                conn.execute(f"UPDATE image_jobs SET {', '.join(fields)} WHERE job_id = ?", tuple(params))
                conn.commit()
            finally:
                conn.close()

    def _fetch_job_record(self, job_id: str) -> Optional[ImageJobRecord]:
        with self._db_lock:
            conn = sqlite3.connect(self.db_path, timeout=10)
            try:
                row = conn.execute(
                    """
                    SELECT job_id, prompt, provider, model, width, height, steps, cfg, seed, mode, status,
                           session_id, created_at, updated_at, started_at, completed_at, duration_ms,
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
            model,
            width,
            height,
            steps,
            cfg,
            seed,
            mode,
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
            model=model,
            width=int(width),
            height=int(height),
            steps=int(steps),
            cfg=float(cfg) if cfg is not None else None,
            seed=int(seed) if seed is not None else None,
            mode=mode,
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

    # Утилиты -------------------------------------------------------------

    def _enforce_rate_limit(
        self,
        bucket: Dict[Any, Deque[float]],
        key: Any,
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
        base = 0.5 + attempt * 0.5
        jitter = random.uniform(0.1, 0.4)
        return min(5.0, base + jitter)

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

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


image_manager = ImageGenerationManager()


__all__ = [
    "ImageGenerationManager",
    "ImageGenerationError",
    "image_manager",
]
