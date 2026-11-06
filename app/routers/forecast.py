from datetime import date, datetime, timedelta

from app import models
from app.database import get_db
from app.deps import ensure_school_access, get_current_user, require_roles
from app.schemas import (
    AdjustmentInput,
    ApproveInput,
    ForecastAdjustmentOut,
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
        raise HTTPException(404, "Школа не найдена")
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
        raise HTTPException(404, "Школа не найдена")
    appr = (
        db.query(models.ForecastApproval).filter_by(school_id=school_id, date=forecast_date).first()
    )
    if appr:
        appr.approved_at = datetime.now()
        appr.approved_by_id = user.id
        appr.comment = payload.comment or ""
    else:
        db.add(
            models.ForecastApproval(
                id=f"appr-{school_id}-{forecast_date.isoformat()}",
                school_id=school_id,
                date=forecast_date,
                approved_at=datetime.now(),
                approved_by_id=user.id,
                comment=payload.comment or "",
            )
        )
    db.commit()
    return compute_forecast(db, school, forecast_date)


@router.get("/schools/{school_id}/forecast/adjustments", response_model=list[ForecastAdjustmentOut])
def get_adjustments(
    school_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    return [
        {
            "id": a.id,
            "school_id": a.school_id,
            "date": a.date,
            "delta": a.delta,
            "reason": a.reason,
            "created_by": db.get(models.User, a.created_by_id).full_name
            if a.created_by_id
            else None,
            "created_at": a.created_at,
        }
        for a in db.query(models.ForecastAdjustment).filter_by(school_id=school_id).all()
    ]


@router.post("/schools/{school_id}/forecast/{target_date}/adjust", response_model=ForecastOut)
def adjust_forecast(
    school_id: str,
    target_date: date,
    payload: AdjustmentInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    adj = (
        db.query(models.ForecastAdjustment).filter_by(school_id=school_id, date=target_date).first()
    )
    if adj:
        adj.delta = payload.delta
        adj.reason = payload.reason
        adj.created_by_id = user.id
    else:
        db.add(
            models.ForecastAdjustment(
                id=f"adj-{school_id}-{target_date.isoformat()}",
                school_id=school_id,
                date=target_date,
                delta=payload.delta,
                reason=payload.reason,
                created_by_id=user.id,
            )
        )
    db.commit()
    return compute_forecast(db, db.get(models.School, school_id), target_date)


@router.delete("/schools/{school_id}/forecast/{target_date}/adjust", status_code=204)
def delete_adjustment(
    school_id: str,
    target_date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    adj = (
        db.query(models.ForecastAdjustment).filter_by(school_id=school_id, date=target_date).first()
    )
    if adj:
        db.delete(adj)
        db.commit()


@router.get("/schools/{school_id}/forecast/history", response_model=list[ForecastHistoryRow])
def forecast_history(
    school_id: str,
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin", "canteen")),
):
    ensure_school_access(user, school_id)
    school = db.get(models.School, school_id)
    rows = []
    for delta in range(days, 0, -1):
        d = date.today() - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        fc = compute_forecast(db, school, d)
        actual = sum(
            max(
                0,
                len(db.query(models.Student).filter_by(class_id=c.id).all())
                - sum(
                    1
                    for s in db.query(models.Student).filter_by(class_id=c.id).all()
                    if s.meal_status == "optOut"
                )
                - len(
                    set(
                        db.query(models.AttendanceRecord)
                        .filter_by(class_id=c.id, date=d)
                        .first()
                        .absent_student_ids
                        or []
                    )
                    if db.query(models.AttendanceRecord).filter_by(class_id=c.id, date=d).first()
                    else set()
                ),
            )
            for c in db.query(models.SchoolClass).filter_by(school_id=school_id).all()
        )
        waste = max(0, fc["total_portions"] - actual)
        rows.append(
            {
                "date": d,
                "forecast": fc["total_portions"],
                "actual": actual,
                "waste_portions": waste,
                "waste_cost": round(waste * 4.2, 2),
                "accuracy": round(
                    min(fc["total_portions"], actual) / max(fc["total_portions"], actual, 1), 3
                ),
                "confidence": fc["confidence"],
                "buffer_percent": fc["buffer_percent"],
            }
        )
    return rows
