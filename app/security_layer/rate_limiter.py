from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request, status

from app.logging import get_logger


logger = get_logger()


@dataclass(slots=True)
class RateLimitConfig:
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, str], Deque[float]] = {}

    def hit(self, key: str, identifier: str, config: RateLimitConfig) -> None:
        now = time.time()
        bucket_key = (key, identifier)
        bucket = self._buckets.setdefault(bucket_key, deque())

        while bucket and now - bucket[0] > config.window_seconds:
            bucket.popleft()

        if len(bucket) >= config.limit:
            logger.warning(
                "[RATE LIMIT] Triggered key=%s id=%s limit=%s window=%ss",
                key,
                identifier,
                config.limit,
                config.window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Превышен лимит обращений ({config.limit} за {config.window_seconds}с)",
            )

        bucket.append(now)


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter

