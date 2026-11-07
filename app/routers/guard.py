from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import AccessEvent, School, SchoolClass, Student
from ..schemas import AccessEventInput
from ..utils import parse_date

router = APIRouter(prefix="/schools", tags=["guard"])


def _event_to_out(e: AccessEvent, db) -> dict:
    student = db.get(Student, e.student_id)
    klass = db.get(SchoolClass, student.class_id) if student else None
    return {
        "id": e.id,
        "schoolId": e.school_id,
        "studentId": e.student_id,
        "studentName": student.full_name if student else None,
        "className": klass.name if klass else None,
        "type": e.type,
        "source": e.source,
        "date": e.date.isoformat(),
        "time": e.time,
    }


@router.get("/{school_id}/access-events")
def list_events(school_id: str, db: DB, user: CurrentUser, date: str | None = None):
    ensure_school_access(user, school_id)
    target = parse_date(date)
    events = (
        db.query(AccessEvent)
        .filter(AccessEvent.school_id == school_id, AccessEvent.date == target)
        .order_by(AccessEvent.time.desc())
        .all()
    )
    return [_event_to_out(e, db) for e in events]


@router.post("/{school_id}/access-events/manual", status_code=201)
def create_event(school_id: str, data: AccessEventInput, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin", "guard"):
        raise HTTPException(403, "Недостаточно прав")
    student = db.get(Student, data.studentId)
    if not student or student.school_id != school_id:
        raise HTTPException(404, "Ученик не найден в этой школе")
    school = db.get(School, school_id)
    try:
        now = datetime.now(ZoneInfo("Europe/Minsk"))
    except Exception:
        now = datetime.now()
    e = AccessEvent(
        school_id=school_id,
        student_id=student.id,
        type=data.type,
        source="manual",
        date=now.date(),
        time=now.strftime("%H:%M"),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _event_to_out(e, db)
