import math
from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_tz(tz: str = "Europe/Minsk") -> date:
    try:
        return datetime.now(ZoneInfo(tz)).date()
    except Exception:
        return date.today()


def parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def age_group_of(grade: int) -> str:
    if grade <= 4:
        return "junior"
    if grade <= 9:
        return "middle"
    return "senior"


def ceil_int(value: float) -> int:
    return int(math.ceil(max(value, 0)))


def ids_to_str(ids: list[str]) -> str:
    return ",".join(sorted({i for i in ids if i}))


def str_to_ids(s: str | None) -> list[str]:
    if not s:
        return []
    return [i for i in s.split(",") if i]
