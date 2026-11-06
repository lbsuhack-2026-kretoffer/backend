"""Клиент для взаимодействия с AI-сервисом предсказания питания (ai-service).

Отправляет расчёт прогноза бэкенда на ``POST /predict`` и получает скорректированные
поля ``total_portions`` и ``confidence``. Если сервис недоступен или не настроен,
возвращает ``None`` — бэкенд использует свой локальный расчёт (graceful degradation).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger("uvicorn.error")


def adjust_forecast(payload: dict[str, Any]) -> dict[str, Any] | None:
    """
    Отправить прогноз в AI-сервис и получить скорректированные значения.

    :param payload: полный расчёт прогноза (ForecastOut-подобный dict).
    :return: ``{"total_portions": int, "confidence": float}`` или ``None`` при ошибке.
    """
    base_url = settings.ml_service_url
    if not base_url:
        return None

    url = base_url.rstrip("/") + "/predict"
    try:
        with httpx.Client(timeout=settings.ml_service_timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.info(
                "AI-сервис скорректировал прогноз: "
                f"total_portions={data.get('total_portions')}, "
                f"confidence={data.get('confidence')}"
            )
            return data
    except Exception as exc:
        logger.warning(f"AI-сервис недоступен ({url}): {exc}")
        return None
