"""Клиент для взаимодействия с ai-service (ML Service API).

Отправляет собранный бэкендом прогноз на POST /predict и получает
ML-скорректированные значения total_portions, confidence, forecast_days и т.д.
"""

from datetime import date, timedelta
from typing import Any

import httpx

from .config import settings
from .models import Attendance, SchoolClass, Student
from .utils import str_to_ids


# ---------------------------------------------------------------------------
# Погода для Минска (Беларусь) через Open-Meteo — бесплатно, без API-ключа
# ---------------------------------------------------------------------------
MINSK_LAT = 53.9
MINSK_LON = 27.5667

# Коды погоды Open-Meteo, по которым считается, что шёл дождь / снег
WEATHER_CODES_RAINY = {
    51, 53, 55,  # морось
    56, 57,      # заморозки
    61, 63, 65,  # дождь
    66, 67,      # ледяной дождь
    71, 73, 75,  # снег
    77,          # снежная крупа
    80, 81, 82,  # ливни
    85, 86,      # снегопад
    95, 96, 99,  # грозы
}


def get_weather_for_minsk(days: int = 5) -> dict[str, dict]:
    """Запрашивает прогноз погоды для Минска у Open-Meteo.

    Возвращает словарь { "YYYY-MM-DD": { temp_celsius, precipitation_mm,
    is_rainy, is_cold } }.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={MINSK_LAT}&longitude={MINSK_LON}&"
        f"hourly=temperature_2m,precipitation,weathercode&"
        f"daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum&"
        f"timezone=Europe/Minsk"
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return {}
            data = resp.json()
    except Exception:
        return {}

    result: dict[str, dict] = {}
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_maxs = daily.get("temperature_2m_max", [])
    temp_mins = daily.get("temperature_2m_min", [])
    precip_sums = daily.get("precipitation_sum", [])
    weather_codes = daily.get("weathercode", [])

    for i, d in enumerate(dates):
        if i >= days:
            break
        tmax = temp_maxs[i] if i < len(temp_maxs) else 15.0
        tmin = temp_mins[i] if i < len(temp_mins) else 15.0
        avg_temp = (tmax + tmin) / 2
        precip = precip_sums[i] if i < len(precip_sums) else 0.0
        wcode = weather_codes[i] if i < len(weather_codes) else 0

        result[d] = {
            "temp_celsius": round(avg_temp, 1),
            "precipitation_mm": round(precip, 1),
            "is_rainy": 1 if wcode in WEATHER_CODES_RAINY else 0,
            "is_cold": 1 if avg_temp < 10.0 else 0,
        }

    return result


# ---------------------------------------------------------------------------
# История посещаемости для расчёта ML-признаков
# ---------------------------------------------------------------------------
def get_historical_attendance(
    db, school_id: str, target: date
) -> dict[str, Any]:
    """Собирает историю посещаемости школы за последние 10 дней.

    Возвращает поля: present_avg_3d, present_avg_7d, present_trend,
    present_yesterday, present_t_minus_2, present_t_minus_3,
    present_same_dow_last_week.
    """
    classes = db.query(SchoolClass).filter(SchoolClass.school_id == school_id).all()
    class_ids = [c.id for c in classes]

    if not class_ids:
        return {
            "present_avg_3d": None,
            "present_avg_7d": None,
            "present_trend": None,
            "present_yesterday": None,
            "present_t_minus_2": None,
            "present_t_minus_3": None,
            "present_same_dow_last_week": None,
        }

    # Посещаемость за последние 10 дней (включая сегодня)
    start_date = target - timedelta(days=9)
    records = (
        db.query(Attendance)
        .filter(
            Attendance.class_id.in_(class_ids),
            Attendance.date >= start_date,
            Attendance.date <= target,
        )
        .all()
    )

    absent_lookup: dict[tuple[str, date], int] = {}
    for r in records:
        absent_ids = str_to_ids(r.absent_ids)
        absent_lookup[(r.class_id, r.date)] = len(absent_ids)

    # Число учеников (без opt_out) в каждом классе
    students_per_class: dict[str, dict[str, int]] = {}
    for c in classes:
        students = db.query(Student).filter(Student.class_id == c.id).all()
        students_per_class[c.id] = {
            "total": len(students),
            "opt_outs": sum(1 for s in students if s.meal_status == "opt_out"),
        }

    # Присутствовало в каждую дату
    date_present: dict[date, int] = {}
    for i in range(10):
        d = target - timedelta(days=i)
        total_present = 0
        for c in classes:
            info = students_per_class.get(c.id, {"total": 0, "opt_outs": 0})
            absent = absent_lookup.get((c.id, d), 0)
            total_present += max(0, info["total"] - info["opt_outs"] - absent)
        date_present[d] = total_present

    present_today = date_present.get(target, 0)

    yesterday = target - timedelta(days=1)
    present_yesterday = date_present.get(yesterday, present_today)

    t_minus_2 = target - timedelta(days=2)
    present_t_minus_2 = date_present.get(t_minus_2, present_today)

    t_minus_3 = target - timedelta(days=3)
    present_t_minus_3 = date_present.get(t_minus_3, present_today)

    last_3 = [date_present.get(target - timedelta(days=i), present_today) for i in range(3)]
    last_7 = [date_present.get(target - timedelta(days=i), present_today) for i in range(7)]

    present_avg_3d = round(sum(last_3) / len(last_3), 1) if last_3 else float(present_today)
    present_avg_7d = round(sum(last_7) / len(last_7), 1) if last_7 else float(present_today)
    present_trend = round(float(present_today - present_yesterday), 1)

    same_dow = target - timedelta(days=7)
    present_same_dow_last_week = date_present.get(same_dow, present_today)

    return {
        "present_avg_3d": present_avg_3d,
        "present_avg_7d": present_avg_7d,
        "present_trend": present_trend,
        "present_yesterday": present_yesterday,
        "present_t_minus_2": present_t_minus_2,
        "present_t_minus_3": present_t_minus_3,
        "present_same_dow_last_week": present_same_dow_last_week,
    }


# ---------------------------------------------------------------------------
# Основная функция запроса к ai-service
# ---------------------------------------------------------------------------
def get_ml_prediction(
    forecast_data: dict[str, Any],
    db=None,
    school_id: str | None = None,
) -> dict[str, Any] | None:
    """Отправить прогноз в ai-service и вернуть ML-результат или None при ошибке."""
    ml_url = settings.ml_service_url
    if not ml_url:
        return None

    by_age = forecast_data.get("byAgeGroup", [])
    age_group = by_age[0].get("ageGroup", "middle") if by_age else "middle"

    target_date_str = forecast_data.get("date")
    target_date = date.today()
    if target_date_str:
        try:
            target_date = date.fromisoformat(target_date_str)
        except Exception:
            pass

    # Погода для Минска
    weather = get_weather_for_minsk(days=5)

    # История посещаемости
    hist: dict[str, Any] = {}
    if db is not None and school_id:
        hist = get_historical_attendance(db, school_id, target_date)

    payload: dict[str, Any] = {
        "school_id": forecast_data.get("schoolId", ""),
        "school_name": forecast_data.get("schoolName"),
        "age_group": age_group,
        "date": forecast_data.get("date"),
        "meal_plan": forecast_data.get("mealPlan", "fixed"),
        "buffer_percent": forecast_data.get("bufferPercent", 0),
        "total_students": forecast_data.get("totalStudents", 0),
        "opt_outs": forecast_data.get("optOuts", 0),
        "absent": forecast_data.get("absent", 0),
        "present": forecast_data.get("present", 0),
        "total_portions": forecast_data.get("totalPortions", 0),
        "by_age_group": by_age,
        "by_category": forecast_data.get("byCategory", []),
        "marked_classes": forecast_data.get("markedClasses", 0),
        "total_classes": forecast_data.get("totalClasses", 0),
        "based_on_date": forecast_data.get("basedOnDate"),
        "confidence": forecast_data.get("confidence", 0.5),
        "forecast_days": 5,
        "main_dish": None,
        "weather": weather,
        "present_avg_3d": hist.get("present_avg_3d"),
        "present_avg_7d": hist.get("present_avg_7d"),
        "present_trend": hist.get("present_trend"),
        "present_yesterday": hist.get("present_yesterday"),
        "present_t_minus_2": hist.get("present_t_minus_2"),
        "present_t_minus_3": hist.get("present_t_minus_3"),
        "present_same_dow_last_week": hist.get("present_same_dow_last_week"),
        "is_holiday_calendar": None,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{ml_url.rstrip('/')}/predict", json=payload)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None
