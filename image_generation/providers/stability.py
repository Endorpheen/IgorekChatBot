from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Dict, List, Optional

import requests

from .base import (
    DEFAULT_CFG,
    DEFAULT_SEED_RANGE,
    DEFAULT_STEPS,
    GenerateResult,
    ProviderError,
    ProviderErrorCode,
    ProviderModelSpec,
    apply_limit_defaults,
)

_BASE_URL = os.getenv("STABILITY_API_BASE", "https://api.stability.ai/v2beta")
_RECOMMENDED_MODELS = {
    "stable-diffusion-xl-v1",
    "stable-diffusion-v1-6",
}


class StabilityAdapter:
    provider_id = "stability"

    def list_models(self, key: str, *, force: bool = False) -> List[ProviderModelSpec]:  # noqa: D401
        headers = {"Authorization": f"Bearer {key}"}
        try:
            response = requests.get(f"{_BASE_URL}/models", headers=headers, timeout=20)
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Stability не ответил вовремя при discovery") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось получить список моделей Stability") from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Stability отклонён")
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Stability ограничил частоту", retry_after=retry_after)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Stability недоступен")
        if response.status_code >= 400:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Stability отклонил запрос: HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Некорректный ответ Stability при discovery") from exc

        models: List[ProviderModelSpec] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str):
                continue
            capabilities = item.get("capabilities") or {}
            if isinstance(capabilities, dict):
                tasks = capabilities.get("type") or capabilities.get("types") or []
            else:
                tasks = []
            if isinstance(tasks, str):
                tasks = [tasks]
            tasks = [task.lower() for task in tasks if isinstance(task, str)]
            if not any("text-to-image" in task or "image" in task for task in tasks):
                continue

            display_name = item.get("name") or model_id
            limits: Dict[str, Any] = {}
            defaults: Dict[str, Any] = {}
            # Stability может отдавать размеры в metadata.default_settings
            default_settings = item.get("default_settings") or {}
            if isinstance(default_settings, dict):
                width = default_settings.get("image_dimensions", {}).get("width")
                height = default_settings.get("image_dimensions", {}).get("height")
                steps = default_settings.get("steps")
                cfg = default_settings.get("cfg_scale")
                if isinstance(width, int) and isinstance(height, int):
                    defaults["width"] = width
                    defaults["height"] = height
                    limits.setdefault("width_values", [width])
                    limits.setdefault("height_values", [height])
                if isinstance(steps, int):
                    defaults["steps"] = steps
                    limits["min_steps"] = steps
                    limits["max_steps"] = max(steps, defaults.get("steps", steps))
                if isinstance(cfg, (int, float)):
                    defaults["cfg"] = float(cfg)

            spec: ProviderModelSpec = {
                "id": model_id,
                "display_name": display_name,
                "recommended": model_id in _RECOMMENDED_MODELS,
                "capabilities": {
                    "supports_steps": True,
                    "supports_cfg": True,
                    "supports_seed": True,
                    "supports_mode": False,
                },
                "limits": limits,
                "defaults": defaults,
            }
            models.append(apply_limit_defaults(spec))

        return models

    def search_models(self, query: str, key: str, *, limit: int = 50) -> List[ProviderModelSpec]:  # noqa: D401
        raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Поиск моделей для Stability не поддерживается")

    def validate_params(
        self,
        model_id: str,
        params: Dict[str, Any],
        *,
        model_spec: Optional[ProviderModelSpec] = None,
    ) -> Dict[str, Any]:
        if not model_spec:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Модель Stability не найдена")

        limits = model_spec.get("limits", {})
        defaults = model_spec.get("defaults", {})

        try:
            width = int(params.get("width", defaults.get("width")))
            height = int(params.get("height", defaults.get("height")))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректный размер изображения") from exc

        if width < limits.get("min_width", width) or width > limits.get("max_width", width):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Ширина выходит за допустимые пределы")
        if height < limits.get("min_height", height) or height > limits.get("max_height", height):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Высота выходит за допустимые пределы")

        try:
            steps = int(params.get("steps", defaults.get("steps", DEFAULT_STEPS)))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректное значение steps") from exc
        if steps < limits.get("min_steps", steps) or steps > limits.get("max_steps", steps):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Steps превышает лимиты модели")

        try:
            cfg = float(params.get("cfg", defaults.get("cfg", DEFAULT_CFG)))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректное значение CFG") from exc
        if cfg < limits.get("min_cfg", cfg) or cfg > limits.get("max_cfg", cfg):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "CFG выходит за допустимые пределы")

        raw_seed = params.get("seed")
        if raw_seed in (None, ""):
            seed = random.randint(*DEFAULT_SEED_RANGE)
        else:
            try:
                seed = int(raw_seed)
            except (TypeError, ValueError) as exc:
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Seed должен быть целым числом") from exc
            if seed < DEFAULT_SEED_RANGE[0] or seed > DEFAULT_SEED_RANGE[1]:
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Seed выходит за пределы допустимого диапазона")

        return {
            "model": model_id,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "seed": seed,
        }

    async def generate(self, prompt: str, params: Dict[str, Any], key: str):  # type: ignore[override]
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "image/png",
        }
        form = {
            "prompt": (None, prompt),
            "mode": (None, "text-to-image"),
            "steps": (None, str(params["steps"])),
            "cfg_scale": (None, str(params["cfg"])),
            "width": (None, str(params["width"])),
            "height": (None, str(params["height"])),
            "seed": (None, str(params.get("seed", 0))),
            "output_format": (None, "png"),
        }

        url = f"{_BASE_URL}/stable-image/generate/{params['model']}"

        try:
            response = await asyncio.to_thread(
                lambda: requests.post(url, headers=headers, files=form, timeout=40)
            )
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Stability не завершил генерацию вовремя") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось вызвать Stability") from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Stability отклонён")
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Stability достиг лимита", retry_after=retry_after)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Stability недоступен")
        if response.status_code >= 400:
            try:
                error_payload = response.json()
            except ValueError:
                error_payload = {}
            message = error_payload.get("message") if isinstance(error_payload, dict) else None
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, message or "Stability отклонил запрос")

        return GenerateResult(image_bytes=response.content, mime_type=response.headers.get("Content-Type", "image/png"))


__all__ = ["StabilityAdapter"]
