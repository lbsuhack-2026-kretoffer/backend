from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import Attendance, ClassTeacher, SchoolClass, Student, User
from ..schemas import ClassPatch, StudentInput, TeacherAssign
from ..utils import parse_date, str_to_ids

router = APIRouter(prefix="/classes", tags=["classes"])


def _get_class(db, class_id) -> SchoolClass:
    c = db.get(SchoolClass, class_id)
    if not c:
        raise HTTPException(404, "Класс не найден")
    return c


@router.get("/{class_id}")
def get_class(class_id: str, db: DB, user: CurrentUser, date: str | None = None):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    target = parse_date(date)
    links = db.query(ClassTeacher).filter(ClassTeacher.class_id == c.id).all()
    teachers = [db.get(User, l.teacher_id) for l in links]  # noqa F741
    teachers = [t for t in teachers if t]
    students_count = db.query(Student).filter(Student.class_id == c.id).count()
    opt = (
        db.query(Student).filter(Student.class_id == c.id, Student.meal_status == "opt_out").count()
    )
    rec = (
        db.query(Attendance).filter(Attendance.class_id == c.id, Attendance.date == target).first()
    )
    attendance = None
    if rec:
        submitter = db.get(User, rec.submitted_by) if rec.submitted_by else None
        attendance = {
            "status": "submitted",
            "absentCount": len(str_to_ids(rec.absent_ids)),
            "submittedAt": rec.submitted_at.isoformat() if rec.submitted_at else None,
            "submittedByName": submitter.full_name if submitter else None,
        }
    return {
        "id": c.id,
        "schoolId": c.school_id,
        "name": c.name,
        "grade": c.grade,
        "ageGroup": c.age_group,
        "teacherIds": [t.id for t in teachers],
        "teacherNames": [t.full_name for t in teachers],
        "studentsCount": students_count,
        "optOutsCount": opt,
        "attendance": attendance,
    }


@router.patch("/{class_id}")
def patch_class(class_id: str, data: ClassPatch, db: DB, user: CurrentUser):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    if data.name is not None:
        c.name = data.name
    if data.grade is not None:
        c.grade = data.grade
    if data.ageGroup is not None:
        c.age_group = data.ageGroup
    if data.teacherId is not None:
        db.query(ClassTeacher).filter(ClassTeacher.class_id == c.id).delete()
        db.add(ClassTeacher(class_id=c.id, teacher_id=data.teacherId))
    db.commit()
    db.refresh(c)
    return get_class(class_id, db, user)


@router.delete("/{class_id}", status_code=204)
def delete_class(class_id: str, db: DB, user: CurrentUser):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    db.delete(c)
    db.commit()
    return None


@router.get("/{class_id}/students")
def list_students(class_id: str, db: DB, user: CurrentUser):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    students = db.query(Student).filter(Student.class_id == c.id).order_by(Student.full_name).all()
    return [
        {
            "id": s.id,
            "schoolId": s.school_id,
            "classId": s.class_id,
            "fullName": s.full_name,
            "mealStatus": s.meal_status,
            "ageGroup": s.age_group,
            "cardNumber": s.card_number,
            "className": c.name,
        }
        for s in students
    ]


@router.post("/{class_id}/students", status_code=201)
def add_student(class_id: str, data: StudentInput, db: DB, user: CurrentUser):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    s = Student(
        school_id=c.school_id,
        class_id=c.id,
        full_name=data.fullName,
        meal_status=data.mealStatus,
        age_group=c.age_group,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {
        "id": s.id,
        "schoolId": s.school_id,
        "classId": s.class_id,
        "fullName": s.full_name,
        "mealStatus": s.meal_status,
        "ageGroup": s.age_group,
        "cardNumber": s.card_number,
        "className": c.name,
    }


@router.post("/{class_id}/teacher")
def set_teacher(class_id: str, data: TeacherAssign, db: DB, user: CurrentUser):
    c = _get_class(db, class_id)
    ensure_school_access(user, c.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    t = db.get(User, data.teacherId)
    if not t or t.school_id != c.school_id or t.role != "teacher":
        raise HTTPException(400, "Учитель не найден в этой школе")
    if (
        not db.query(ClassTeacher)
        .filter(ClassTeacher.class_id == c.id, ClassTeacher.teacher_id == t.id)
        .first()
    ):
        db.add(ClassTeacher(class_id=c.id, teacher_id=t.id))
        db.commit()
    return get_class(class_id, db, user)
