from datetime import date, timedelta
from math import ceil

from app import models
from app.services.ml_client import ask_ml_for_correction
from sqlalchemy.orm import Session

CONFIDENCE_HISTORY_DAYS = 3
CANTEEN_PARTICIPATION = 0.88  # доля присутствующих, реально покупающих еду


def _get_attendance(db: Session, class_id: str, target: date):
    return db.query(models.AttendanceRecord).filter_by(class_id=class_id, date=target).first()


def _get_fallback_attendance(db: Session, class_id: str, target: date):
    return (
        db.query(models.AttendanceRecord)
        .filter(
            models.AttendanceRecord.class_id == class_id,
            models.AttendanceRecord.date <= target,
        )
        .order_by(models.AttendanceRecord.date.desc())
        .first()
    )


def _history_days(db: Session, school_id: str) -> int:
    class_ids = [c.id for c in db.query(models.SchoolClass).filter_by(school_id=school_id).all()]
    if not class_ids:
        return 0
    dates = (
        db.query(models.AttendanceRecord.date)
        .filter(models.AttendanceRecord.class_id.in_(class_ids))
        .distinct()
        .all()
    )
    return len(dates)


def compute_forecast(db: Session, school: models.School, target: date) -> dict:
    classes = db.query(models.SchoolClass).filter_by(school_id=school.id).all()
    total_classes = len(classes)
    marked = 0
    total_students = 0
    total_optouts = 0
    total_absent = 0
    dates_used: list[date] = []
    by_group: dict[str, dict] = {}

    for cls in classes:
        students = db.query(models.Student).filter_by(class_id=cls.id).all()
        n_students = len(students)
        n_optouts = sum(1 for s in students if s.meal_status == "optOut")
        regular_ids = {s.id for s in students if s.meal_status == "regular"}

        att = _get_attendance(db, cls.id, target)
        used_date = target
        if att:
            marked += 1
            absent_ids = set(att.absent_student_ids or [])
        else:
            fb = _get_fallback_attendance(db, cls.id, target)
            if fb:
                absent_ids = set(fb.absent_student_ids or [])
                used_date = fb.date
            else:
                absent_ids = set()

        absent = len(absent_ids & regular_ids)
        dates_used.append(used_date)
        total_students += n_students
        total_optouts += n_optouts
        total_absent += absent

        g = by_group.setdefault(cls.age_group, {"students": 0, "optOuts": 0, "absent": 0})
        g["students"] += n_students
        g["optOuts"] += n_optouts
        g["absent"] += absent

    present = max(0, total_students - total_optouts - total_absent)
    buffer = school.buffer_percent
    total_portions = ceil(present * (1 + buffer / 100)) if present > 0 else 0

    by_age_group = []
    for name in ("junior", "middle", "senior"):
        if name not in by_group:
            continue
        g = by_group[name]
        g_present = max(0, g["students"] - g["optOuts"] - g["absent"])
        g_portions = ceil(g_present * (1 + buffer / 100)) if g_present > 0 else 0
        by_age_group.append(
            {
                "age_group": name,
                "students": g["students"],
                "opt_outs": g["optOuts"],
                "absent": g["absent"],
                "present": g_present,
                "portions": g_portions,
            }
        )

    based_on_date = min(dates_used) if dates_used else target
    h_days = _history_days(db, school.id)
    coverage = (marked / total_classes) if total_classes else 0
    confidence = round(
        min(0.99, 0.5 + 0.4 * coverage + 0.01 * min(h_days, CONFIDENCE_HISTORY_DAYS)), 2
    )

    base = {
        "school_id": school.id,
        "school_name": school.name,
        "date": target,
        "meal_plan": school.meal_plan,
        "buffer_percent": buffer,
        "total_students": total_students,
        "opt_outs": total_optouts,
        "absent": total_absent,
        "present": present,
        "total_portions": total_portions,
        "by_age_group": by_age_group,
        "by_category": [],
        "marked_classes": marked,
        "total_classes": total_classes,
        "based_on_date": based_on_date,
        "confidence": confidence,
    }

    # ML-коррекция (если сервис доступен)
    if present > 0:
        corrected = ask_ml_for_correction(base)
        if corrected:
            base.update({k: corrected[k] for k in corrected if k in base})

    # Подтягиваем статус подтверждения
    approval = db.query(models.ForecastApproval).filter_by(school_id=school.id, date=target).first()
    if approval:
        approver = db.get(models.User, approval.approved_by_id)
        base["status"] = "approved"
        base["approved_at"] = approval.approved_at
        base["approved_by"] = approver.full_name if approver else None
        base["comment"] = approval.comment or ""
    else:
        base["status"] = "draft"
        base["approved_at"] = None
        base["approved_by"] = None
        base["comment"] = ""

    return base


def compute_canteen_forecast(db: Session, school: models.School, target: date) -> dict:
    base = compute_forecast(db, school, target)
    buffer = school.buffer_percent
    present = base["present"]
    yesterday = target - timedelta(days=1)

    categories = db.query(models.CanteenCategory).filter_by(school_id=school.id).all()

    cat_rows: list[dict] = []
    total_forecast_qty = 0
    expected_revenue = 0.0
    yesterday_total_qty = 0

    for cat in categories:
        qty = (
            ceil(present * CANTEEN_PARTICIPATION * cat.share * (1 + buffer / 100))
            if present > 0
            else 0
        )
        revenue = round(qty * cat.avg_price, 2)
        total_forecast_qty += qty
        expected_revenue += revenue

        y_sale = (
            db.query(models.CanteenSale)
            .filter_by(school_id=school.id, date=yesterday, category_id=cat.id)
            .first()
        )
        y_qty = y_sale.qty if y_sale else 0
        y_waste = y_sale.waste_qty if y_sale else 0
        yesterday_total_qty += y_qty

        history_rows = (
            db.query(models.CanteenSale)
            .filter_by(school_id=school.id, category_id=cat.id)
            .filter(models.CanteenSale.date < target)
            .order_by(models.CanteenSale.date.desc())
            .limit(7)
            .all()
        )
        history = [{"date": r.date, "qty": r.qty, "waste_qty": r.waste_qty} for r in history_rows]

        cat_rows.append(
            {
                "id": cat.id,
                "school_id": cat.school_id,
                "name": cat.name,
                "share": cat.share,
                "avg_price": cat.avg_price,
                "unit": cat.unit,
                "qty": qty,
                "revenue": revenue,
                "yesterday_qty": y_qty,
                "waste_qty": y_waste,
                "history": history,
            }
        )

    base["categories"] = cat_rows
    base["by_category"] = [
        {"id": c["id"], "name": c["name"], "qty": c["qty"], "revenue": c["revenue"]}
        for c in cat_rows
    ]
    base["yesterday_date"] = yesterday
    base["yesterday_total_qty"] = yesterday_total_qty
    base["total_forecast_qty"] = total_forecast_qty
    base["expected_revenue"] = round(expected_revenue, 2)
    return base
