from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import (
    Attendance,
    CanteenCategory,
    ForecastAdjustment,
    ForecastApproval,
    School,
    SchoolClass,
    Student,
    User,
)
from ..ml_client import get_ml_prediction
from ..schemas import AdjustInput, ApproveInput
from ..utils import ceil_int, parse_date, str_to_ids, today_tz

router = APIRouter(prefix="/schools", tags=["forecast"])


def _attendance_for(db, school_id: str, class_ids: list[str], target: date):
    return {
        r.class_id: r
        for r in db.query(Attendance)
        .filter(Attendance.class_id.in_(class_ids), Attendance.date == target)
        .all()
    }


def _build_forecast(db, school: School, target: date) -> dict:
    classes = db.query(SchoolClass).filter(SchoolClass.school_id == school.id).all()
    class_ids = [c.id for c in classes]
    by_class_students = {
        c.id: db.query(Student).filter(Student.class_id == c.id).all() for c in classes
    }
    # ищем отметки на target; если нет — последняя доступная
    records = _attendance_for(db, school.id, class_ids, target)
    used_dates = {r.date for r in records.values()}  # noqa F841
    based_on = target
    if not records:
        last = (
            db.query(Attendance)
            .filter(Attendance.class_id.in_(class_ids))
            .order_by(Attendance.date.desc())
            .first()
        )
        if last:
            records = _attendance_for(db, school.id, class_ids, last.date)
            based_on = last.date

    total_students = sum(len(v) for v in by_class_students.values())
    opt_outs = sum(1 for v in by_class_students.values() for s in v if s.meal_status == "opt_out")
    total_absent = 0
    by_age: dict[str, dict] = {}
    present_by_age: dict[str, int] = {}

    for c in classes:
        students = by_class_students[c.id]
        rec = records.get(c.id)
        absent_ids = str_to_ids(rec.absent_ids) if rec else []
        total_absent += len(absent_ids)
        absent_set = set(absent_ids)
        group = by_age.setdefault(
            c.age_group,
            {"ageGroup": c.age_group, "students": 0, "optOuts": 0, "absent": 0, "present": 0},
        )
        group["students"] += len(students)
        group["absent"] += len(absent_set)
        for s in students:
            if s.meal_status == "opt_out":
                group["optOuts"] += 1
                continue
            if s.id in absent_set:
                continue
            group["present"] += 1
            present_by_age[c.age_group] = present_by_age.get(c.age_group, 0) + 1

    present = total_students - opt_outs - total_absent
    present = max(present, 0)
    base_portions = ceil_int(present * (1 + school.buffer_percent / 100))

    adj = (
        db.query(ForecastAdjustment)
        .filter(ForecastAdjustment.school_id == school.id, ForecastAdjustment.date == target)
        .first()
    )
    delta = adj.delta if adj else 0
    total_portions = max(0, base_portions + delta)

    approval = (
        db.query(ForecastApproval)
        .filter(ForecastApproval.school_id == school.id, ForecastApproval.date == target)
        .first()
    )

    marked = len(records)
    total_classes = len(classes)

    # byCategory (для шведского стола)
    by_category = []
    if school.meal_plan == "canteen":
        cats = db.query(CanteenCategory).filter(CanteenCategory.school_id == school.id).all()
        for cat in cats:
            qty = ceil_int(present * 0.88 * cat.share * (1 + school.buffer_percent / 100))
            by_category.append(
                {
                    "id": cat.id,
                    "name": cat.name,
                    "share": cat.share,
                    "avgPrice": cat.avg_price,
                    "unit": cat.unit,
                    "qty": qty,
                }
            )

    approver = db.get(User, approval.approved_by) if approval and approval.approved_by else None
    by_age_list = [
        {
            "ageGroup": g["ageGroup"],
            "students": g["students"],
            "optOuts": g["optOuts"],
            "absent": g["absent"],
            "present": g["present"],
            "portions": ceil_int(g["present"] * (1 + school.buffer_percent / 100)),
        }
        for g in by_age.values()
    ]

    confidence = 0.9 if marked == total_classes and total_classes else 0.6

    # --- ML-коррекция через ai-service ---
    ml_result = None
    _forecast_payload = {
        "schoolId": school.id,
        "schoolName": school.name,
        "date": target.isoformat(),
        "mealPlan": school.meal_plan,
        "bufferPercent": school.buffer_percent,
        "totalStudents": total_students,
        "optOuts": opt_outs,
        "absent": total_absent,
        "present": present,
        "totalPortions": total_portions,
        "adjustmentDelta": delta,
        "byAgeGroup": by_age_list,
        "byCategory": by_category,
        "markedClasses": marked,
        "totalClasses": total_classes,
        "basedOnDate": based_on.isoformat(),
        "confidence": confidence,
    }
    ml_result = get_ml_prediction(_forecast_payload, db=db, school_id=school.id)
    if ml_result:
        total_portions = ml_result.get("total_portions", total_portions)
        confidence = ml_result.get("confidence", confidence)

    # Если нейросеть скорректировала итог, пересчитаем порции по возрастным группам
    # пропорционально новому итогу, чтобы разбивка соответствовала ИИ-прогнозу
    if ml_result and total_portions > 0:
        base_sum = sum(g["portions"] for g in by_age_list)
        if base_sum > 0:
            running_sum = 0
            updated = []
            for i, g in enumerate(by_age_list):
                if i == len(by_age_list) - 1:
                    # последняя группа забирает остаток, чтобы сумма сошлась с итогом
                    portions = max(0, total_portions - running_sum)
                else:
                    portions = max(0, int(g["portions"] / base_sum * total_portions))
                running_sum += portions
                updated.append({**g, "portions": portions})
            by_age_list = updated

    return {
        "schoolId": school.id,
        "schoolName": school.name,
        "date": target.isoformat(),
        "mealPlan": school.meal_plan,
        "bufferPercent": school.buffer_percent,
        "totalStudents": total_students,
        "optOuts": opt_outs,
        "absent": total_absent,
        "present": present,
        "totalPortions": total_portions,
        "adjustmentDelta": delta,
        "adjustmentReason": adj.reason if adj else None,
        "byAgeGroup": by_age_list,
        "byCategory": by_category,
        "markedClasses": marked,
        "totalClasses": total_classes,
        "basedOnDate": based_on.isoformat(),
        "confidence": confidence,
        "status": "approved" if approval else "draft",
        "approvedAt": approval.approved_at.isoformat() if approval else None,
        "approvedBy": approver.full_name if approver else None,
        "comment": approval.comment if approval else None,
        "mlModelUsed": ml_result.get("model_used") if ml_result else None,
        "mlForecastDays": ml_result.get("forecast_days") if ml_result else None,
        "mlCategories": ml_result.get("categories") if ml_result else None,
    }


@router.get("/{school_id}/forecast")
def get_forecast(school_id: str, db: DB, user: CurrentUser, date: str | None = None):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    return _build_forecast(db, school, parse_date(date))


@router.post("/{school_id}/forecast/{date_str}/approve")
def approve_forecast(school_id: str, date_str: str, data: ApproveInput, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    target = parse_date(date_str)
    approval = (
        db.query(ForecastApproval)
        .filter(ForecastApproval.school_id == school_id, ForecastApproval.date == target)
        .first()
    )
    if approval:
        approval.comment = data.comment
        approval.approved_by = user.id
    else:
        db.add(
            ForecastApproval(
                school_id=school_id,
                date=target,
                comment=data.comment,
                approved_by=user.id,
            )
        )
    db.commit()
    return _build_forecast(db, school, target)


@router.get("/{school_id}/forecast/history")
def forecast_history(school_id: str, db: DB, user: CurrentUser, days: int = 14):
    ensure_school_access(user, school_id)
    end = today_tz()
    start = end - timedelta(days=days - 1)
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    rows = []
    d = end
    while d >= start:
        f = _build_forecast(db, school, d)
        rows.append(f)
        d -= timedelta(days=1)
    return rows


@router.get("/{school_id}/forecast/adjustments")
def list_adjustments(school_id: str, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    items = (
        db.query(ForecastAdjustment)
        .filter(ForecastAdjustment.school_id == school_id)
        .order_by(ForecastAdjustment.date.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "schoolId": a.school_id,
            "date": a.date.isoformat(),
            "delta": a.delta,
            "reason": a.reason,
            "createdBy": a.created_by,
            "createdAt": a.created_at.isoformat() if a.created_at else None,
        }
        for a in items
    ]


@router.post("/{school_id}/forecast/{date_str}/adjust")
def adjust_forecast(school_id: str, date_str: str, data: AdjustInput, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    target = parse_date(date_str)
    adj = (
        db.query(ForecastAdjustment)
        .filter(ForecastAdjustment.school_id == school_id, ForecastAdjustment.date == target)
        .first()
    )
    if adj:
        adj.delta = data.delta
        adj.reason = data.reason
        adj.created_by = user.id
    else:
        db.add(
            ForecastAdjustment(
                school_id=school_id,
                date=target,
                delta=data.delta,
                reason=data.reason,
                created_by=user.id,
            )
        )
    db.commit()
    return _build_forecast(db, school, target)


@router.delete("/{school_id}/forecast/{date_str}/adjust", status_code=204)
def delete_adjustment(school_id: str, date_str: str, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin", "canteen"):
        raise HTTPException(403, "Недостаточно прав")
    target = parse_date(date_str)
    adj = (
        db.query(ForecastAdjustment)
        .filter(ForecastAdjustment.school_id == school_id, ForecastAdjustment.date == target)
        .first()
    )
    if adj:
        db.delete(adj)
        db.commit()
    return None
