from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlencode, urljoin

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

_LOGGER = logging.getLogger(__name__)

_RECOMMENDED_MODELS = {
    "stability-ai/sdxl",
    "black-forest-labs/flux-1.1-pro",
    "black-forest-labs/flux-1.1-schnell",
    "black-forest-labs/flux-1.1-dev",
}

_FALLBACK_MODEL_IDS = (
    "black-forest-labs/flux-1.1-schnell",
    "black-forest-labs/flux-1.1-dev",
    "stability-ai/sdxl",
)

_FEATURED_MODEL_IDS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            "bytedance/seedream-3",
            "bytedance/seedream-4",
            "black-forest-labs/flux-schnell",
            "black-forest-labs/flux-1.1-pro",
            "black-forest-labs/flux-1.1-pro-ultra",
            "black-forest-labs/flux-pro",
            "black-forest-labs/flux-dev",
            "black-forest-labs/flux-kontext-pro",
            "black-forest-labs/flux-kontext-max",
            "ideogram-ai/ideogram-v3-turbo",
            "ideogram-ai/ideogram-v3-quality",
            "ideogram-ai/ideogram-v3-balanced",
            "ideogram-ai/ideogram-v2",
            "ideogram-ai/ideogram-v2a",
            "ideogram-ai/ideogram-v2-turbo",
            "ideogram-ai/ideogram-v2a-turbo",
            "google/imagen-3",
            "google/imagen-3-fast",
            "google/imagen-4",
            "google/imagen-4-fast",
            "google/imagen-4-ultra",
            "google/nano-banana",
            "qwen/qwen-image",
            "tencent/hunyuan-image-3",
            "stability-ai/sdxl",
            "stability-ai/stable-diffusion-3.5-large",
            "stability-ai/stable-diffusion-3.5-large-turbo",
            "stability-ai/stable-diffusion-3.5-medium",
            "recraft-ai/recraft-v3",
            "recraft-ai/recraft-v3-svg",
            "leonardoai/lucid-origin",
            "bria/image-3.2",
            "minimax/image-01",
            "luma/photon",
            "luma/photon-flash",
            "playgroundai/playground-v2.5",
            "ai-forever/kandinsky-2",
            "ai-forever/kandinsky-2.2",
            "runwayml/gen3-alpha",
            "fofr/any-comfyui-workflow",
            "nvidia/sana",
            "nvidia/sana-sprint-1.6b",
            "prunaai/hidream-l1-fast",
            "prunaai/hidream-l1-full",
            "prunaai/hidream-l1-dev",
            "prunaai/flux.1-dev",
            "prunaai/wan-2.2-image",
            "prunaai/sdxl-lightning",
            "prunaai/sdxl-lightning-4step",
            "datacte/proteus-v0.2",
            "datacte/proteus-v0.3",
            "lucataco/dreamshaper-xl-turbo",
            "lucataco/realistic-vision-v5.1",
            "lucataco/ssd-1b",
            "lucataco/open-dalle-v1.1",
            "adirik/realvisxl-v3.0-turbo",
            "adirik/realvisxl-v3-multi-controlnet-lora",
            "jagilley/controlnet-scribble",
            "tstramer/material-diffusion",
            "fermatresearch/sdxl-controlnet-lora",
            "fermatresearch/sdxl-multi-controlnet-lora",
            "lucataco/realvisxl-v3-multi-controlnet-lora",
            "stability-ai/stable-diffusion",
        ]
    ).keys()
)

_BASE_URL = os.getenv("REPLICATE_API_BASE", "https://api.replicate.com/v1")


class ReplicateAdapter:
    provider_id = "replicate"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._details_cache: Dict[str, Dict[str, Any]] = {}

    def list_models(self, key: str, *, force: bool = False) -> List[ProviderModelSpec]:  # noqa: D401
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }

        aggregated: Dict[str, ProviderModelSpec] = {}

        # 1. Коллекция "image-generation" — curated набор
        try:
            collection_payload = self._request_json(f"{_BASE_URL}/collections/image-generation", headers)
            for item in self._extract_items(collection_payload):
                self._add_model_candidate(item, headers, aggregated, from_collection=True)
        except ProviderError as exc:
            if exc.code == ProviderErrorCode.UNAUTHORIZED:
                raise
            _LOGGER.debug("Replicate collection discovery пропущен: %s", exc)

        # 2. Поиск популярных моделей (FLUX, SDXL, SD)
        search_terms = ["flux", "sdxl", "stable diffusion", "image"]
        max_total = 200
        for term in search_terms:
            next_url: Optional[str] = f"{_BASE_URL}/models?{urlencode({'search': term, 'limit': 50})}"
            page = 0
            while next_url and page < 5 and len(aggregated) < max_total:
                payload = self._request_json(next_url, headers)
                for item in self._extract_items(payload):
                    self._add_model_candidate(item, headers, aggregated, from_collection=False)
                    if len(aggregated) >= max_total:
                        break
                next_url = self._extract_next(payload)
                page += 1

        # 3. Фолбэк, если ничего не нашли
        if not aggregated:
            fallback = self._build_fallback_models(headers)
            aggregated.update(fallback)

        models = list(aggregated.values())
        models.sort(key=lambda spec: (spec.get("recommended") is not True, spec.get("display_name", spec["id"])) )
        return models

    def search_models(self, query: str, key: str, *, limit: int = 50) -> List[ProviderModelSpec]:  # noqa: D401
        query = (query or "").strip()
        if not query:
            return []

        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }

        aggregated: Dict[str, ProviderModelSpec] = {}
        max_total = max(1, min(limit, 200))
        next_url: Optional[str] = f"{_BASE_URL}/models?{urlencode({'search': query, 'limit': min(50, max_total)})}"
        page = 0
        max_pages = 5

        while next_url and page < max_pages and len(aggregated) < max_total:
            payload = self._request_json(next_url, headers)
            for item in self._extract_items(payload):
                self._add_model_candidate(item, headers, aggregated, from_collection=False)
                if len(aggregated) >= max_total:
                    break
            next_url = self._extract_next(payload)
            page += 1

        models = list(aggregated.values())
        normalized_query = query.lower()
        models = [
            spec for spec in models
            if normalized_query in (spec.get("display_name") or "").lower()
            or normalized_query in spec.get("id", "").lower()
        ]
        models.sort(key=lambda spec: (spec.get("recommended") is not True, spec.get("display_name", spec["id"])))
        if len(models) > max_total:
            models = models[:max_total]
        return models

    def get_featured_models(self, key: str) -> List[ProviderModelSpec]:  # noqa: D401
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }

        featured: Dict[str, ProviderModelSpec] = {}
        for full_id in _FEATURED_MODEL_IDS:
            owner, sep, name = full_id.partition("/")
            if not sep:
                continue

            spec: Optional[ProviderModelSpec]
            details = self._fetch_model_details(owner, name, headers)
            if details:
                spec = self._normalise_model(details, headers, from_collection=True)
            else:
                spec = None

            if not spec:
                spec = self._build_placeholder_spec(full_id)

            spec["recommended"] = True
            featured[spec["id"]] = spec

        return list(featured.values())

    def validate_params(
        self,
        model_id: str,
        params: Dict[str, Any],
        *,
        model_spec: Optional[ProviderModelSpec] = None,
    ) -> Dict[str, Any]:
        if not model_spec:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Модель Replicate не найдена")

        limits = model_spec.get("limits", {})
        defaults = model_spec.get("defaults", {})

        try:
            width = int(params.get("width", defaults.get("width")))
            height = int(params.get("height", defaults.get("height")))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректный размер изображения") from exc

        if width < limits.get("min_width", width) or width > limits.get("max_width", width):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Ширина выходит за пределы модели")
        if height < limits.get("min_height", height) or height > limits.get("max_height", height):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Высота выходит за пределы модели")

        try:
            steps = int(params.get("steps", defaults.get("steps", DEFAULT_STEPS)))
        except (TypeError, ValueError) as exc:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Некорректное значение steps") from exc
        if steps < limits.get("min_steps", steps) or steps > limits.get("max_steps", steps):
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, "Steps превышает лимит для модели")

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

        metadata = model_spec.get("metadata", {})
        version_id = metadata.get("version_id")
        input_fields = metadata.get("input_fields", [])

        return {
            "model": model_id,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg": cfg,
            "seed": seed,
            "version_id": version_id,
            "input_fields": input_fields,
        }

    async def generate(self, prompt: str, params: Dict[str, Any], key: str):  # type: ignore[override]
        version_id = params.get("version_id")
        if not isinstance(version_id, str):
            raise ProviderError(ProviderErrorCode.INTERNAL, "Для модели Replicate не указан version_id")

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        input_payload = self._build_input_payload(prompt, params)

        try:
            response = await asyncio.to_thread(
                lambda: self._session.post(
                    f"{_BASE_URL}/predictions",
                    headers=headers,
                    json={"version": version_id, "input": input_payload},
                    timeout=40,
                )
            )
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Replicate не ответил вовремя") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось выполнить запрос к Replicate") from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Replicate отклонён")
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Replicate достиг лимита", retry_after=retry_after)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Replicate временно недоступен")
        if response.status_code >= 400:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Replicate отклонил генерацию: HTTP {response.status_code}")

        try:
            prediction_data = response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Некорректный ответ Replicate при генерации") from exc

        prediction_id = prediction_data.get("id")
        if not isinstance(prediction_id, str):
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Replicate вернул ответ без ID задачи")

        deadline = time.monotonic() + 40.0
        status = prediction_data.get("status")
        while status in {"starting", "processing", "queued"}:
            await asyncio.sleep(1.0)
            if time.monotonic() > deadline:
                raise ProviderError(ProviderErrorCode.TIMEOUT, "Replicate не завершил генерацию вовремя")
            try:
                prediction_resp = await asyncio.to_thread(
                    lambda: self._session.get(f"{_BASE_URL}/predictions/{prediction_id}", headers=headers, timeout=20)
                )
            except requests.Timeout:
                continue
            except requests.RequestException as exc:
                raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Ошибка при опросе статуса Replicate") from exc

            if prediction_resp.status_code == 429:
                retry_after = float(prediction_resp.headers.get("Retry-After", "0") or 0)
                raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Replicate ограничил частоту опроса", retry_after=retry_after)
            if prediction_resp.status_code >= 500:
                continue
            if prediction_resp.status_code >= 400:
                raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Replicate отклонил запрос статуса: HTTP {prediction_resp.status_code}")
            try:
                prediction_data = prediction_resp.json()
            except ValueError:
                continue
            status = prediction_data.get("status")

        if status != "succeeded":
            error_message = prediction_data.get("error") or "Replicate завершил задачу с ошибкой"
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, str(error_message))

        output = prediction_data.get("output")
        image_url: Optional[str] = None
        if isinstance(output, list) and output:
            first = output[0]
            if isinstance(first, str):
                image_url = first
        elif isinstance(output, str):
            image_url = output

        if not image_url:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Replicate не вернул ссылку на изображение")

        try:
            image_resp = await asyncio.to_thread(lambda: self._session.get(image_url, timeout=40))
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Истек таймаут загрузки изображения Replicate") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Не удалось загрузить результат Replicate") from exc

        if image_resp.status_code >= 400:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Replicate вернул ошибку при загрузке изображения")

        return GenerateResult(image_bytes=image_resp.content, mime_type=image_resp.headers.get("Content-Type", "image/png"))

    def _build_input_payload(self, prompt: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"prompt": prompt}
        input_fields = {str(field).lower() for field in params.get("input_fields", [])}
        width = params["width"]
        height = params["height"]
        steps = params["steps"]
        cfg = params["cfg"]
        seed = params.get("seed")

        allow_defaults = not input_fields

        if "num_inference_steps" in input_fields or allow_defaults:
            payload["num_inference_steps"] = steps
        elif "steps" in input_fields:
            payload["steps"] = steps

        if "guidance_scale" in input_fields or allow_defaults:
            payload["guidance_scale"] = cfg
        elif "cfg_scale" in input_fields:
            payload["cfg_scale"] = cfg

        if "width" in input_fields or allow_defaults:
            payload["width"] = width
        if "height" in input_fields or allow_defaults:
            payload["height"] = height
        if "image_dimensions" in input_fields:
            payload["image_dimensions"] = f"{width}x{height}"

        if seed is not None and ("seed" in input_fields or allow_defaults):
            payload["seed"] = seed

        return payload

    def _request_json(self, url: str, headers: Dict[str, str]) -> Any:
        try:
            response = self._session.get(url, headers=headers, timeout=30)
        except requests.Timeout as exc:
            raise ProviderError(ProviderErrorCode.TIMEOUT, "Replicate не ответил вовремя") from exc
        except requests.RequestException as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Ошибка сети при обращении к Replicate") from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorCode.UNAUTHORIZED, "Ключ Replicate отклонён")
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "0") or 0)
            raise ProviderError(ProviderErrorCode.RATE_LIMIT, "Replicate ограничил частоту запросов", retry_after=retry_after)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Сервис Replicate временно недоступен")
        if response.status_code >= 400:
            raise ProviderError(ProviderErrorCode.BAD_REQUEST, f"Replicate отклонил запрос: HTTP {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorCode.PROVIDER_ERROR, "Некорректный JSON от Replicate") from exc

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("results", "models", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _extract_next(self, payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            next_url = payload.get("next")
            if isinstance(next_url, str) and next_url:
                if next_url.startswith("http"):
                    return next_url
                return urljoin(_BASE_URL + "/", next_url.lstrip("/"))
        return None

    def _add_model_candidate(
        self,
        item: Dict[str, Any],
        headers: Dict[str, str],
        aggregated: Dict[str, ProviderModelSpec],
        *,
        from_collection: bool,
    ) -> None:
        spec = self._normalise_model(item, headers, from_collection=from_collection)
        if spec:
            aggregated[spec["id"]] = spec

    def _normalise_model(
        self,
        item: Dict[str, Any],
        headers: Dict[str, str],
        *,
        from_collection: bool,
    ) -> Optional[ProviderModelSpec]:
        owner, name = self._extract_owner_name(item)
        if not owner or not name:
            return None
        full_id = f"{owner}/{name}"

        if not self._is_image_candidate(full_id, item, from_collection):
            return None

        version_id, input_fields = self._extract_version_metadata(item)
        if (not version_id or not input_fields) and owner and name:
            details = self._fetch_model_details(owner, name, headers)
            if details:
                version_id, input_fields = self._extract_version_metadata(details)
                item = {**details, **item}
        if not version_id:
            return None

        display_name = item.get("display_name") or item.get("name") or full_id

        spec: ProviderModelSpec = {
            "id": full_id,
            "display_name": display_name,
            "recommended": full_id in _RECOMMENDED_MODELS,
            "capabilities": {
                "supports_steps": True,
                "supports_cfg": True,
                "supports_seed": True,
                "supports_mode": False,
            },
            "limits": {},
            "defaults": {},
            "metadata": {
                "version_id": version_id,
                "input_fields": sorted(input_fields),
            },
        }

        return apply_limit_defaults(spec)

    def _extract_owner_name(self, item: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        owner = item.get("owner") or item.get("model_owner") or item.get("creator", {}).get("username")
        name = item.get("name") or item.get("model_name") or item.get("slug")

        identifier = item.get("id") or item.get("model")
        if (not owner or not name) and isinstance(identifier, str) and "/" in identifier:
            owner, name = identifier.split("/", 1)

        if isinstance(owner, str):
            owner = owner.strip()
        if isinstance(name, str):
            name = name.strip()

        return owner or None, name or None

    def _is_image_candidate(self, full_id: str, item: Dict[str, Any], from_collection: bool) -> bool:
        if from_collection:
            return True

        lower_id = full_id.lower()
        if any(prefix in lower_id for prefix in ("stable-diffusion", "sdxl", "sd-", "flux", "image", "img")):
            return True

        tags = item.get("tags") or item.get("keywords")
        if isinstance(tags, list):
            lowered = [str(tag).lower() for tag in tags]
            if any("image" in tag or "diffusion" in tag for tag in lowered):
                return True

        description = str(item.get("description") or item.get("summary") or "").lower()
        if any(keyword in description for keyword in ("image", "diffusion", "generate")):
            return True

        latest_version = item.get("latest_version")
        schema = None
        if isinstance(latest_version, dict):
            schema = latest_version.get("openapi_schema")
        if schema and self._schema_outputs_image(schema):
            return True

        return False

    def _extract_version_metadata(self, item: Dict[str, Any]) -> Tuple[Optional[str], Set[str]]:
        version_id: Optional[str] = None
        input_fields: Set[str] = set()

        latest_version = item.get("latest_version")
        if isinstance(latest_version, dict):
            version_id = latest_version.get("id") or latest_version.get("version_id")
            schema = latest_version.get("openapi_schema")
            input_fields.update(self._extract_input_fields(schema))
        elif isinstance(latest_version, str):
            version_id = latest_version

        if not version_id:
            candidate = item.get("latest_version_id") or item.get("version_id")
            if isinstance(candidate, str):
                version_id = candidate

        if not input_fields:
            schema = item.get("openapi_schema")
            input_fields.update(self._extract_input_fields(schema))

        return version_id, input_fields

    @staticmethod
    def _extract_input_fields(schema: Any) -> Set[str]:
        fields: Set[str] = set()
        if not isinstance(schema, dict):
            return fields
        try:
            components = schema.get("components", {})
            schemas = components.get("schemas", {})
            input_schema = schemas.get("Input") or schemas.get("input") or {}
            properties = input_schema.get("properties", {})
            for key in properties.keys():
                fields.add(str(key).lower())
        except AttributeError:
            return fields
        return fields

    @staticmethod
    def _schema_outputs_image(schema: Any) -> bool:
        if not isinstance(schema, dict):
            return False
        components = schema.get("components", {})
        schemas = components.get("schemas", {})
        output_schema = schemas.get("Output") or {}
        properties = output_schema.get("properties", {}) if isinstance(output_schema, dict) else {}
        for key, value in properties.items():
            if isinstance(key, str) and "image" in key.lower():
                return True
            if isinstance(value, dict):
                enum = value.get("enum")
                if isinstance(enum, list) and any("image" in str(item).lower() for item in enum):
                    return True
        return False

    def _fetch_model_details(self, owner: str, name: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        full_id = f"{owner}/{name}"
        if full_id in self._details_cache:
            return self._details_cache[full_id]

        url = f"{_BASE_URL}/models/{owner}/{name}"
        try:
            details = self._request_json(url, headers)
        except ProviderError as exc:
            _LOGGER.debug("Не удалось получить детали модели %s: %s", full_id, exc)
            return None

        if isinstance(details, dict):
            self._details_cache[full_id] = details
            return details
        return None

    def _build_fallback_models(self, headers: Dict[str, str]) -> Dict[str, ProviderModelSpec]:
        fallback: Dict[str, ProviderModelSpec] = {}
        for full_id in _FALLBACK_MODEL_IDS:
            try:
                owner, name = full_id.split("/", 1)
            except ValueError:
                continue
            details = self._fetch_model_details(owner, name, headers)
            if not details:
                continue
            spec = self._normalise_model(details, headers, from_collection=True)
            if spec:
                fallback[spec["id"]] = spec
        return fallback

    def _build_placeholder_spec(self, full_id: str) -> ProviderModelSpec:
        _, _, name = full_id.partition("/")
        display_source = name or full_id
        display = display_source.replace("-", " ").replace("_", " ").replace(".", " ")
        display = " ".join(part.capitalize() for part in display.split()) or full_id

        spec: ProviderModelSpec = {
            "id": full_id,
            "display_name": display,
            "recommended": True,
            "capabilities": {
                "supports_steps": True,
                "supports_cfg": True,
                "supports_seed": True,
                "supports_mode": False,
            },
            "limits": {},
            "defaults": {},
            "metadata": {},
        }
        return apply_limit_defaults(spec)


__all__ = ["ReplicateAdapter"]
