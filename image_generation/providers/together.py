from __future__ import annotations

import asyncio
import binascii
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

_TOGETHER_MODELS_URL = os.getenv("TOGETHER_MODELS_URL", "https://api.together.xyz/v1/models")
_TOGETHER_GENERATE_URL = os.getenv("TOGETHER_GENERATE_URL", "https://api.together.xyz/v1/images/generations")

_RECOMMENDED_MODELS = {
    "black-forest-labs/FLUX.1-schnell-Free",
    "black-forest-labs/FLUX.1-dev",
    "stabilityai/stable-diffusion-xl-base-1.0",
}


class TogetherAdapter:
    provider_id = "together"

    def list_models(self, key: str, *, force: bool = False) -> List[ProviderModelSpec]:  # noqa: D401
        headers = {"Authorization": f"Bearer {key}"}
        try:
            response = requests.get(_TOGETHER_MODELS_URL, headers=headers, timeout=20)
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Превышен таймаут запроса Together") from exc
        except requests.RequestException as exc:  # pragma: no cover - сетевые огр.
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось получить список моделей Together") from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Together отклонён")
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Together ограничил частоту запросов", retry_after=retry_after)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Together временно недоступен")
        if response.status_code >= 400:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Together отклонил запрос: HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Некорректный ответ Together при запросе моделей") from exc

        raw_models = []
        if isinstance(payload, list):
            raw_models = payload
        elif isinstance(payload, dict):
            data = payload.get("data") or payload.get("results") or payload.get("models")
            if isinstance(data, list):
                raw_models = data
        else:
            raw_models = []

        models: List[ProviderModelSpec] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue

            model_id = item.get("id") or item.get("name")
            if not isinstance(model_id, str):
                continue

            task_candidates: List[str] = []
            for key in ("task", "tasks", "type", "types", "capabilities"):
                value = item.get(key)
                if isinstance(value, str):
                    task_candidates.append(value)
                elif isinstance(value, list):
                    task_candidates.extend(str(elem) for elem in value if isinstance(elem, (str, bytes)))
                elif isinstance(value, dict):
                    task_candidates.extend(str(elem) for elem in value.keys())

            task_candidates = [candidate.lower() for candidate in task_candidates if isinstance(candidate, str)]
            if not any("image" in candidate or "img" in candidate for candidate in task_candidates):
                continue

            display_name = item.get("display_name") or item.get("name") or model_id
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
                "limits": {},
                "defaults": {},
            }

            limits = spec["limits"]
            defaults = spec["defaults"]
            meta_limits = item.get("limits") or {}
            if isinstance(meta_limits, dict):
                steps_limits = meta_limits.get("steps") or {}
                if isinstance(steps_limits, dict):
                    min_steps = steps_limits.get("min")
                    max_steps = steps_limits.get("max")
                    if isinstance(min_steps, int):
                        limits["min_steps"] = min_steps
                    if isinstance(max_steps, int):
                        limits["max_steps"] = max_steps
                cfg_limits = meta_limits.get("cfg") or meta_limits.get("guidance") or {}
                if isinstance(cfg_limits, dict):
                    min_cfg = cfg_limits.get("min")
                    max_cfg = cfg_limits.get("max")
                    if isinstance(min_cfg, (int, float)):
                        limits["min_cfg"] = float(min_cfg)
                    if isinstance(max_cfg, (int, float)):
                        limits["max_cfg"] = float(max_cfg)
                size_limits = meta_limits.get("size") or {}
                if isinstance(size_limits, dict):
                    for key_name, target in (("min_width", "min_width"), ("max_width", "max_width"), ("min_height", "min_height"), ("max_height", "max_height")):
                        value = size_limits.get(target)
                        if isinstance(value, int):
                            limits[key_name] = value
            defaults.update({
                "steps": DEFAULT_STEPS,
                "cfg": DEFAULT_CFG,
            })
            spec.setdefault("metadata", {})
            if isinstance(spec["metadata"], dict):
                spec["metadata"].update({
                    "task": task_candidates,
                })

            models.append(apply_limit_defaults(spec))

        return models

    def validate_params(
        self,
        model_id: str,
        params: Dict[str, Any],
        *,
        model_spec: Optional[ProviderModelSpec] = None,
    ) -> Dict[str, Any]:
        if not model_spec:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Модель Together не найдена")

        limits = model_spec.get("limits", {})
        defaults = model_spec.get("defaults", {})
        capabilities = model_spec.get("capabilities", {})

        try:
            width = int(params.get("width", defaults.get("width")))
            height = int(params.get("height", defaults.get("height")))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректный размер изображения") from exc

        min_width = limits.get("min_width", width)
        max_width = limits.get("max_width", width)
        min_height = limits.get("min_height", height)
        max_height = limits.get("max_height", height)

        if width < min_width or width > max_width:
            raise ProviderError(
                ProviderErrorCode.BAD_REQUEST,
                f"Ширина выходит за пределы модели ({min_width}..{max_width})",
            )
        if height < min_height or height > max_height:
            raise ProviderError(
                ProviderErrorCode.BAD_REQUEST,
                f"Высота выходит за пределы модели ({min_height}..{max_height})",
            )

        steps = defaults.get("steps", DEFAULT_STEPS)
        if capabilities.get("supports_steps", True):
            try:
                steps = int(params.get("steps", steps))
            except (TypeError, ValueError) as exc:
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректное значение steps") from exc
            if steps < limits.get("min_steps", steps) or steps > limits.get("max_steps", steps):
                raise ProviderError(
                    ProviderErrorCode.BAD_REQUEST,
                    f"Steps превышает лимиты модели ({limits.get('min_steps')}..{limits.get('max_steps')})",
                )

        cfg = defaults.get("cfg", DEFAULT_CFG)
        if capabilities.get("supports_cfg", True):
            try:
                cfg = float(params.get("cfg", cfg))
            except (TypeError, ValueError) as exc:
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректное значение CFG") from exc
            if cfg < limits.get("min_cfg", cfg) or cfg > limits.get("max_cfg", cfg):
                raise ProviderError(
                    ProviderErrorCode.BAD_REQUEST,
                    f"CFG выходит за пределы модели ({limits.get('min_cfg')}..{limits.get('max_cfg')})",
                )

        seed: Optional[int]
        if capabilities.get("supports_seed", True):
            raw_seed = params.get("seed")
            if raw_seed in (None, ""):
                seed = random.randint(*DEFAULT_SEED_RANGE)
            else:
                try:
                    seed = int(raw_seed)
                except (TypeError, ValueError) as exc:
                    raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Seed должен быть целым числом") from exc
                if seed < DEFAULT_SEED_RANGE[0] or seed > DEFAULT_SEED_RANGE[1]:
                    raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Seed выходит за допустимый диапазон")
        else:
            seed = None

        mode = None
        if capabilities.get("supports_mode"):
            available_modes = {option["id"] for option in capabilities.get("modes", []) if isinstance(option, dict) and "id" in option}
            if available_modes:
                raw_mode = params.get("mode")
                if raw_mode not in available_modes:
                    raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Выбран неподдерживаемый режим модели")
                mode = str(raw_mode)

        return {
            "model": model_id,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "seed": seed,
            "mode": mode,
        }

    async def generate(self, prompt: str, params: Dict[str, Any], key: str):  # type: ignore[override]
        """Запускает генерацию изображения."""

        payload: Dict[str, Any] = {
            "model": params["model"],
            "prompt": prompt,
            "width": params["width"],
            "height": params["height"],
            "steps": params["steps"],
            "n": 1,
            "response_format": "b64_json",
            "image_format": "webp",
        }
        if params.get("cfg") is not None:
            payload["guidance_scale"] = params["cfg"]
        if params.get("seed") is not None:
            payload["seed"] = params["seed"]
        if params.get("mode"):
            payload["mode"] = params["mode"]

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        def _request() -> requests.Response:
            return requests.post(_TOGETHER_GENERATE_URL, headers=headers, json=payload, timeout=40)

        try:
            response = await asyncio.to_thread(_request)
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Генерация Together превысила таймаут") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сеть недоступна для Together") from exc

        status = response.status_code
        if status in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Together отклонён")
        if status == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Together достиг лимитов", retry_after=retry_after)
        if status >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Together недоступен")
        if status >= 400:
            message = self._extract_error_message(response) or "Together отклонил запрос"
            if "model" in message.lower() and "access" in message.lower():
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Модель недоступна для ключа Together")
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, message)

        try:
            payload_json = response.json()
            data = payload_json.get("data")
            if not isinstance(data, list) or not data:
                raise ValueError("data")
            first = data[0]
            b64_value = first.get("b64_json")
            if not isinstance(b64_value, str):
                raise ValueError("b64_json")
        except (ValueError, TypeError) as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Ответ Together не содержит изображение") from exc

        import base64

        try:
            image_bytes = base64.b64decode(b64_value)
        except (ValueError, binascii.Error) as exc:  # type: ignore[name-defined]
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось декодировать изображение Together") from exc

        return GenerateResult(image_bytes=image_bytes, mime_type="image/webp")

    @staticmethod
    def _extract_error_message(response: requests.Response) -> Optional[str]:
        try:
            payload = response.json()
        except ValueError:
            return None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    return message
            message = payload.get("message")
            if isinstance(message, str):
                return message
        return None


__all__ = ["TogetherAdapter"]
