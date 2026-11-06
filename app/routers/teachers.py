from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser
from ..models import Attendance, ClassTeacher, School, SchoolClass, Student
from ..utils import parse_date, str_to_ids

router = APIRouter(prefix="/teachers", tags=["teachers"])


def _teacher_classes(db, teacher_id: str):
    return (
        db.query(SchoolClass)
        .join(ClassTeacher, ClassTeacher.class_id == SchoolClass.id)
        .filter(ClassTeacher.teacher_id == teacher_id)
        .all()
    )


@router.get("/me/classes")
def my_classes(db: DB, user: CurrentUser, date: str | None = None):
    if user.role != "teacher":
        raise HTTPException(403, "Доступно только учителям")
    target = parse_date(date)
    classes = _teacher_classes(db, user.id)
    school = db.get(School, user.school_id) if user.school_id else None
    return {
        "schoolId": user.school_id,
        "schoolName": school.name if school else None,
        "date": target.isoformat(),
        "deadline": school.attendance_deadline if school else None,
        "classes": [
            {
                "id": c.id,
                "name": c.name,
                "grade": c.grade,
                "ageGroup": c.age_group,
                "studentsCount": db.query(Student).filter(Student.class_id == c.id).count(),
                "attendance": (
                    lambda rec: None
                    if not rec
                    else {
                        "status": "submitted",
                        "absentCount": len(str_to_ids(rec.absent_ids)),
                        "submittedAt": rec.submitted_at.isoformat() if rec.submitted_at else None,
                    }
                )(
                    db.query(Attendance)
                    .filter(Attendance.class_id == c.id, Attendance.date == target)
                    .first()
                ),
            }
            for c in classes
        ],
    }


@router.get("/me/attendance")
def my_attendance(db: DB, user: CurrentUser, days: int = 14):
    if user.role != "teacher":
        raise HTTPException(403, "Доступно только учителям")
    from datetime import date as _d
    from datetime import timedelta

    end = _d.today()
    start = end - timedelta(days=days - 1)
    class_ids = [c.id for c in _teacher_classes(db, user.id)]
    if not class_ids:
        return {"date": end.isoformat(), "days": days, "items": []}
    records = (
        db.query(Attendance)
        .filter(
            Attendance.class_id.in_(class_ids), Attendance.date >= start, Attendance.date <= end
        )
        .order_by(Attendance.date.desc())
        .all()
    )
    cls_names = {
        c.id: c.name for c in db.query(SchoolClass).filter(SchoolClass.id.in_(class_ids)).all()
    }
    return {
        "date": end.isoformat(),
        "days": days,
        "items": [
            {
                "date": r.date.isoformat(),
                "classId": r.class_id,
                "className": cls_names.get(r.class_id),
                "absentCount": len(str_to_ids(r.absent_ids)),
                "submittedAt": r.submitted_at.isoformat() if r.submitted_at else None,
            }
            for r in records
        ],
    }
