import httpx
from app.config import settings


def ask_ml_for_correction(payload: dict) -> dict | None:
    """
    Если задан ML_SERVICE_URL — отправляем ему базовый расчёт
    и получаем скорректированный прогноз.
    Формат ответа должен совпадать с Forecast (см. api.md).
    """
    if not settings.ml_service_url:
        return None
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.post(f"{settings.ml_service_url}/predict", json=payload)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        return None
    return None
