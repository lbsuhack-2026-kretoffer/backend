from datetime import date, datetime

from app import models
from app.database import get_db
from app.deps import ensure_school_access, require_roles
from app.schemas import AccessEventOut, ManualAccessInput
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(tags=["skud"])


def _event_out(db: Session, e: models.AccessEvent) -> dict:
    student = db.get(models.Student, e.student_id)
    cls = db.get(models.SchoolClass, student.class_id) if student else None
    return {
        "id": e.id,
        "school_id": e.school_id,
        "student_id": e.student_id,
        "student_name": student.full_name if student else "",
        "class_name": cls.name if cls else "",
        "type": e.type,
        "source": e.source,
        "date": e.date,
        "time": e.time,
    }


@router.get("/schools/{school_id}/access-events", response_model=list[AccessEventOut])
def list_events(
    school_id: str,
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("guard", "school_admin")),
):
    ensure_school_access(user, school_id)
    events = (
        db.query(models.AccessEvent)
        .filter_by(school_id=school_id, date=date)
        .order_by(models.AccessEvent.time.desc())
        .all()
    )
    return [_event_out(db, e) for e in events]


@router.post(
    "/schools/{school_id}/access-events/manual",
    response_model=AccessEventOut,
    status_code=201,
)
def manual_event(
    school_id: str,
    payload: ManualAccessInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("guard")),
):
    ensure_school_access(user, school_id)
    if payload.type not in ("entry", "exit"):
        raise HTTPException(status_code=400, detail="type должен быть entry или exit")
    student = db.get(models.Student, payload.student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(status_code=404, detail="Ученик не найден в этой школе")

    now = datetime.now()
    event = models.AccessEvent(
        id=f"evt-{db.query(models.AccessEvent).count() + 1}",
        school_id=school_id,
        student_id=student.id,
        type=payload.type,
        source="manual",
        date=now.date(),
        time=now.strftime("%H:%M"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_out(db, event)
