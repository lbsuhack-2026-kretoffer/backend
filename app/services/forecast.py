from datetime import date, timedelta
from math import ceil

from app import models
from sqlalchemy.orm import Session


def compute_forecast(db: Session, school: models.School, target: date) -> dict:
    classes = db.query(models.SchoolClass).filter_by(school_id=school.id).all()
    total_students, total_optouts, total_absent, marked = 0, 0, 0, 0
    by_group = {}

    for cls in classes:
        students = db.query(models.Student).filter_by(class_id=cls.id).all()
        n_opt = sum(1 for s in students if s.meal_status == "optOut")
        reg_ids = {s.id for s in students if s.meal_status == "regular"}

        att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=target).first()
        if not att:
            att = (
                db.query(models.AttendanceRecord)
                .filter_by(class_id=cls.id)
                .filter(models.AttendanceRecord.date <= target)
                .order_by(models.AttendanceRecord.date.desc())
                .first()
            )
        else:
            marked += 1

        absent_ids = set(att.absent_student_ids or []) if att else set()
        n_abs = len(absent_ids & reg_ids)

        total_students += len(students)
        total_optouts += n_opt
        total_absent += n_abs
        g = by_group.setdefault(cls.age_group, {"students": 0, "optOuts": 0, "absent": 0})
        g["students"] += len(students)
        g["optOuts"] += n_opt
        g["absent"] += n_abs

    present = max(0, total_students - total_optouts - total_absent)
    base_portions = ceil(present * (1 + school.buffer_percent / 100)) if present > 0 else 0

    adj = db.query(models.ForecastAdjustment).filter_by(school_id=school.id, date=target).first()
    delta = adj.delta if adj else 0
    total_portions = max(0, base_portions + delta)

    by_age_group = []
    for name in ("junior", "middle", "senior"):
        if name in by_group:
            g = by_group[name]
            g_pres = max(0, g["students"] - g["optOuts"] - g["absent"])
            by_age_group.append(
                {
                    "age_group": name,
                    "students": g["students"],
                    "opt_outs": g["optOuts"],
                    "absent": g["absent"],
                    "present": g_pres,
                    "portions": ceil(g_pres * (1 + school.buffer_percent / 100)) if g_pres else 0,
                }
            )

    appr = db.query(models.ForecastApproval).filter_by(school_id=school.id, date=target).first()
    approver = db.get(models.User, appr.approved_by_id) if appr else None

    return {
        "school_id": school.id,
        "school_name": school.name,
        "date": target,
        "meal_plan": school.meal_plan,
        "buffer_percent": school.buffer_percent,
        "total_students": total_students,
        "opt_outs": total_optouts,
        "absent": total_absent,
        "present": present,
        "total_portions": total_portions,
        "adjustment_delta": delta,
        "adjustment_reason": adj.reason if adj else None,
        "by_age_group": by_age_group,
        "by_category": [],
        "marked_classes": marked,
        "total_classes": len(classes),
        "based_on_date": target,
        "confidence": 0.9,
        "status": "approved" if appr else "draft",
        "approved_at": appr.approved_at if appr else None,
        "approved_by": approver.full_name if approver else None,
        "comment": appr.comment if appr else "",
    }


def compute_canteen_forecast(db: Session, school: models.School, target: date) -> dict:
    base = compute_forecast(db, school, target)
    cats = db.query(models.CanteenCategory).filter_by(school_id=school.id).all()

    cat_rows, total_qty, rev = [], 0, 0.0
    for c in cats:
        qty = (
            ceil(base["present"] * 0.88 * c.share * (1 + school.buffer_percent / 100))
            if base["present"] > 0
            else 0
        )
        r = round(qty * c.avg_price, 2)
        total_qty += qty
        rev += r
        cat_rows.append(
            {
                "id": c.id,
                "school_id": c.school_id,
                "name": c.name,
                "share": c.share,
                "avg_price": c.avg_price,
                "unit": c.unit,
                "qty": qty,
                "revenue": r,
                "yesterday_qty": 0,
                "waste_qty": 0,
                "history": [],
            }
        )

    base.update(
        {
            "categories": cat_rows,
            "by_category": [
                {"id": c["id"], "name": c["name"], "qty": c["qty"], "revenue": c["revenue"]}
                for c in cat_rows
            ],
            "yesterday_date": target - timedelta(days=1),
            "yesterday_total_qty": 0,
            "total_forecast_qty": total_qty,
            "expected_revenue": rev,
        }
    )
    return base
