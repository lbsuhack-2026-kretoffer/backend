from datetime import date, datetime, timedelta

from app import models
from app.database import get_db
from app.deps import ensure_school_access, get_current_user, require_roles
from app.schemas import (
    ApproveInput,
    ForecastHistoryRow,
    ForecastOut,
)
from app.services.forecast import compute_forecast
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter(tags=["forecast"])


@router.get("/schools/{school_id}/forecast", response_model=ForecastOut)
def get_forecast(
    school_id: str,
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ensure_school_access(user, school_id)
    school = db.get(models.School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    return compute_forecast(db, school, date)


@router.post("/schools/{school_id}/forecast/{forecast_date}/approve", response_model=ForecastOut)
def approve_forecast(
    school_id: str,
    forecast_date: date,
    payload: ApproveInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    school = db.get(models.School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")

    approval = (
        db.query(models.ForecastApproval).filter_by(school_id=school_id, date=forecast_date).first()
    )
    now = datetime.now()
    if approval:
        approval.approved_at = now
        approval.approved_by_id = user.id
        approval.comment = payload.comment or ""
    else:
        approval = models.ForecastApproval(
            id=f"appr-{school_id}-{forecast_date.isoformat()}",
            school_id=school_id,
            date=forecast_date,
            approved_at=now,
            approved_by_id=user.id,
            comment=payload.comment or "",
        )
        db.add(approval)
    db.commit()
    return compute_forecast(db, school, forecast_date)


@router.get("/schools/{school_id}/forecast/history", response_model=list[ForecastHistoryRow])
def forecast_history(
    school_id: str,
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    school = db.get(models.School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")

    rows = []
    today = date.today()
    for delta in range(days, 0, -1):
        d = today - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        fc = compute_forecast(db, school, d)
        # факт: считаем по отметкам на этот же день (или fallback не нужен — берём прямые данные)
        classes = db.query(models.SchoolClass).filter_by(school_id=school_id).all()
        actual_present = 0
        for cls in classes:
            students = db.query(models.Student).filter_by(class_id=cls.id).all()
            n_opt = sum(1 for s in students if s.meal_status == "optOut")
            regular_ids = {s.id for s in students if s.meal_status == "regular"}
            att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=d).first()
            n_absent = len(set(att.absent_student_ids or []) & regular_ids) if att else 0
            actual_present += max(0, len(students) - n_opt - n_absent)

        forecast_portions = fc["total_portions"]
        actual_portions = actual_present
        waste = max(0, forecast_portions - actual_portions)
        accuracy = round(
            min(forecast_portions, actual_portions) / max(forecast_portions, actual_portions, 1),
            3,
        )
        rows.append(
            {
                "date": d,
                "forecast": forecast_portions,
                "actual": actual_portions,
                "waste_portions": waste,
                "waste_cost": round(waste * 4.2, 2),
                "accuracy": accuracy,
                "confidence": fc["confidence"],
                "buffer_percent": fc["buffer_percent"],
            }
        )
    return rows
