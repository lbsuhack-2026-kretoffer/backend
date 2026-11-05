from datetime import date, datetime, timedelta

from app import models
from app.database import get_db
from app.deps import ensure_school_access, get_current_user, require_roles, teacher_class_ids
from app.schemas import (
    AttendanceOut,
    AttendancePutInput,
    AttendanceSummaryOut,
    TeacherAttendanceOut,
    TeacherClassesOut,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter(tags=["attendance"])


def _build_attendance_out(db: Session, cls: models.SchoolClass, d: date) -> dict:
    school = db.get(models.School, cls.school_id)
    students = db.query(models.Student).filter_by(class_id=cls.id).all()
    opt_outs = sum(1 for s in students if s.meal_status == "optOut")
    att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=d).first()
    absent_ids = set(att.absent_student_ids or []) if att else set()
    submitted_by = db.get(models.User, att.submitted_by_id) if att else None

    student_marks = [
        {
            "id": s.id,
            "full_name": s.full_name,
            "meal_status": s.meal_status,
            "card_number": s.card_number,
            "absent": s.id in absent_ids,
        }
        for s in students
    ]

    return {
        "class_id": cls.id,
        "class_name": cls.name,
        "school_id": cls.school_id,
        "school_name": school.name if school else "",
        "date": d,
        "deadline": school.attendance_deadline if school else "09:15",
        "status": "marked" if att else "pending",
        "absent_student_ids": list(absent_ids),
        "submitted_at": att.submitted_at.strftime("%H:%M") if att else None,
        "submitted_by_name": submitted_by.full_name if submitted_by else None,
        "total_students": len(students),
        "opt_outs": opt_outs,
        "students": student_marks,
    }


@router.get("/classes/{class_id}/attendance", response_model=AttendanceOut)
def get_attendance(
    class_id: str,
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    if user.role == "teacher" and class_id not in teacher_class_ids(db, user.id):
        raise HTTPException(status_code=403, detail="Класс не назначен учителю")
    return _build_attendance_out(db, cls, date)


@router.put("/classes/{class_id}/attendance", response_model=AttendanceOut)
def put_attendance(
    class_id: str,
    payload: AttendancePutInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("teacher", "school_admin")),  # noqa F821
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    if user.role == "teacher" and class_id not in teacher_class_ids(db, user.id):
        raise HTTPException(status_code=403, detail="Класс не назначен учителю")

    students = db.query(models.Student).filter_by(class_id=class_id).all()
    valid_ids = {s.id for s in students}
    unknown = set(payload.absent_student_ids) - valid_ids
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Ученики не из этого класса: {', '.join(sorted(unknown))}",
        )

    att = db.query(models.AttendanceRecord).filter_by(class_id=class_id, date=payload.date).first()
    now = datetime.now()
    if att:
        att.absent_student_ids = list(payload.absent_student_ids)
        att.submitted_at = now
        att.submitted_by_id = user.id
    else:
        att = models.AttendanceRecord(
            id=f"att-{class_id}-{payload.date.isoformat()}",
            class_id=class_id,
            date=payload.date,
            submitted_at=now,
            submitted_by_id=user.id,
            absent_student_ids=list(payload.absent_student_ids),
        )
        db.add(att)
    db.commit()
    return _build_attendance_out(db, cls, payload.date)


@router.get("/teachers/me/classes", response_model=TeacherClassesOut)
def teacher_classes(
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("teacher")),
):
    school = db.get(models.School, user.school_id) if user.school_id else None
    class_ids = teacher_class_ids(db, user.id)
    classes = (
        db.query(models.SchoolClass)
        .filter(models.SchoolClass.id.in_(class_ids) if class_ids else False)
        .all()
    )
    rows = []
    for cls in classes:
        students = db.query(models.Student).filter_by(class_id=cls.id).all()
        n_opt = sum(1 for s in students if s.meal_status == "optOut")
        regular_ids = {s.id for s in students if s.meal_status == "regular"}
        att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=date).first()
        n_absent = len(set(att.absent_student_ids or []) & regular_ids) if att else 0
        submitted_by = db.get(models.User, att.submitted_by_id) if att else None
        rows.append(
            {
                "id": cls.id,
                "name": cls.name,
                "grade": cls.grade,
                "age_group": cls.age_group,
                "students": len(students),
                "opt_outs": n_opt,
                "absent": n_absent,
                "present": max(0, len(students) - n_opt - n_absent),
                "status": "marked" if att else "pending",
                "submitted_at": att.submitted_at.strftime("%H:%M") if att else None,
                "submitted_by_name": submitted_by.full_name if submitted_by else None,
            }
        )
    return {
        "teacher": {"id": user.id, "full_name": user.full_name},
        "school_name": school.name if school else "",
        "deadline": school.attendance_deadline if school else "09:15",
        "date": date,
        "classes": rows,
    }


@router.get("/teachers/me/attendance", response_model=TeacherAttendanceOut)
def teacher_attendance_history(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("teacher")),
):
    class_ids = teacher_class_ids(db, user.id)
    if not class_ids:
        return {"date": date.today(), "days": days, "items": []}
    since = date.today() - timedelta(days=days)
    records = (
        db.query(models.AttendanceRecord)
        .filter(
            models.AttendanceRecord.class_id.in_(class_ids),
            models.AttendanceRecord.date >= since,
        )
        .order_by(models.AttendanceRecord.date.desc())
        .all()
    )
    items = []
    for rec in records:
        cls = db.get(models.SchoolClass, rec.class_id)
        students = db.query(models.Student).filter_by(class_id=rec.class_id).all()
        regular_ids = {s.id for s in students if s.meal_status == "regular"}
        absent = len(set(rec.absent_student_ids or []) & regular_ids)
        items.append(
            {
                "date": rec.date,
                "class_id": rec.class_id,
                "class_name": cls.name if cls else "",
                "absent_count": absent,
                "submitted_at": rec.submitted_at.strftime("%H:%M"),
                "status": "marked",
            }
        )
    return {"date": date.today(), "days": days, "items": items}


@router.get("/schools/{school_id}/attendance/summary", response_model=AttendanceSummaryOut)
def school_attendance_summary(
    school_id: str,
    date: date,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    ensure_school_access(user, school_id)
    classes = db.query(models.SchoolClass).filter_by(school_id=school_id).all()
    total_students = 0
    opt_outs = 0
    absent = 0
    present = 0
    marked = 0
    rows = []
    for cls in classes:
        students = db.query(models.Student).filter_by(class_id=cls.id).all()
        n_students = len(students)
        n_opt = sum(1 for s in students if s.meal_status == "optOut")
        regular_ids = {s.id for s in students if s.meal_status == "regular"}
        att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=date).first()
        n_absent = len(set(att.absent_student_ids or []) & regular_ids) if att else 0
        submitted_by = db.get(models.User, att.submitted_by_id) if att else None
        if att:
            marked += 1
        total_students += n_students
        opt_outs += n_opt
        absent += n_absent
        present += max(0, n_students - n_opt - n_absent)

        teachers = (
            db.query(models.User)
            .join(models.ClassTeacher, models.ClassTeacher.teacher_id == models.User.id)
            .filter(models.ClassTeacher.class_id == cls.id)
            .all()
        )
        rows.append(
            {
                "id": cls.id,
                "name": cls.name,
                "age_group": cls.age_group,
                "students": n_students,
                "opt_outs": n_opt,
                "absent": n_absent,
                "present": max(0, n_students - n_opt - n_absent),
                "status": "marked" if att else "pending",
                "submitted_at": att.submitted_at.strftime("%H:%M") if att else None,
                "submitted_by_name": submitted_by.full_name if submitted_by else None,
                "teacher_names": [t.full_name for t in teachers],
            }
        )
    return {
        "school_id": school_id,
        "date": date,
        "total_students": total_students,
        "opt_outs": opt_outs,
        "absent": absent,
        "present": present,
        "marked_classes": marked,
        "total_classes": len(classes),
        "classes": rows,
    }
