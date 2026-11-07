from fastapi import APIRouter, HTTPException, status

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import Attendance, ClassTeacher, ForecastApproval, School, SchoolClass, Student, User
from ..schemas import AttendancePut
from ..utils import ids_to_str, parse_date, str_to_ids

router = APIRouter(prefix="/classes", tags=["attendance"])


@router.get("/{class_id}/attendance")
def get_attendance(class_id: str, db: DB, user: CurrentUser, date: str | None = None):
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "Класс не найден")
    ensure_school_access(user, c.school_id)
    target = parse_date(date)
    school = db.get(School, c.school_id)
    students = db.query(Student).filter(Student.class_id == c.id).order_by(Student.full_name).all()
    rec = (
        db.query(Attendance).filter(Attendance.class_id == c.id, Attendance.date == target).first()
    )
    submitter = db.get(User, rec.submitted_by) if rec and rec.submitted_by else None
    return {
        "classId": c.id,
        "className": c.name,
        "schoolId": c.school_id,
        "schoolName": school.name if school else None,
        "date": target.isoformat(),
        "deadline": school.attendance_deadline if school else None,
        "status": "submitted" if rec else "pending",
        "absentStudentIds": str_to_ids(rec.absent_ids) if rec else [],
        "submittedAt": rec.submitted_at.isoformat() if rec and rec.submitted_at else None,
        "submittedByName": submitter.full_name if submitter else None,
        "totalStudents": len(students),
        "optOuts": sum(1 for s in students if s.meal_status == "opt_out"),
        "students": [
            {
                "id": s.id,
                "fullName": s.full_name,
                "mealStatus": s.meal_status,
                "ageGroup": s.age_group,
                "cardNumber": s.card_number,
            }
            for s in students
        ],
    }


@router.put("/{class_id}/attendance")
def put_attendance(class_id: str, data: AttendancePut, db: DB, user: CurrentUser):
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "Класс не найден")
    ensure_school_access(user, c.school_id)
    if user.role not in ("teacher", "school_admin", "platform_admin"):
        raise HTTPException(403, "Недостаточно прав")

    # После подтверждения заявки завучом изменять отсутствующих учеников невозможно
    # data.date уже распарсен Pydantic в объект date, parse_date не нужен
    approval = (
        db.query(ForecastApproval)
        .filter(ForecastApproval.school_id == c.school_id, ForecastApproval.date == data.date)
        .first()
    )
    if approval:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Нельзя изменить отсутствующих учеников: заявка на эту дату уже подтверждена завучом.",
        )

    valid_ids = {s.id for s in db.query(Student).filter(Student.class_id == c.id).all()}
    absent_ids = [i for i in data.absentStudentIds if i in valid_ids]

    rec = (
        db.query(Attendance)
        .filter(Attendance.class_id == c.id, Attendance.date == data.date)
        .first()
    )
    if rec:
        rec.absent_ids = ids_to_str(absent_ids)
        rec.submitted_by = user.id
    else:
        rec = Attendance(
            school_id=c.school_id,
            class_id=c.id,
            date=data.date,
            absent_ids=ids_to_str(absent_ids),
            submitted_by=user.id,
        )
        db.add(rec)
    db.commit()
    db.refresh(rec)

    school = db.get(School, c.school_id)
    students = db.query(Student).filter(Student.class_id == c.id).order_by(Student.full_name).all()
    return {
        "classId": c.id,
        "className": c.name,
        "schoolId": c.school_id,
        "schoolName": school.name if school else None,
        "date": rec.date.isoformat(),
        "deadline": school.attendance_deadline if school else None,
        "status": "submitted",
        "absentStudentIds": str_to_ids(rec.absent_ids),
        "submittedAt": rec.submitted_at.isoformat() if rec.submitted_at else None,
        "submittedByName": user.full_name,
        "totalStudents": len(students),
        "optOuts": sum(1 for s in students if s.meal_status == "opt_out"),
        "students": [
            {
                "id": s.id,
                "fullName": s.full_name,
                "mealStatus": s.meal_status,
                "ageGroup": s.age_group,
                "cardNumber": s.card_number,
            }
            for s in students
        ],
    }
