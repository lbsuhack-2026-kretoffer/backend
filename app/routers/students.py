from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import Student
from ..schemas import StudentPatch

router = APIRouter(prefix="/students", tags=["students"])


@router.patch("/{student_id}")
def patch_student(student_id: str, data: StudentPatch, db: DB, user: CurrentUser):
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Ученик не найден")
    ensure_school_access(user, s.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    if data.fullName is not None:
        s.full_name = data.fullName
    if data.mealStatus is not None:
        s.meal_status = data.mealStatus
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
    }


@router.delete("/{student_id}", status_code=204)
def delete_student(student_id: str, db: DB, user: CurrentUser):
    s = db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Ученик не найден")
    ensure_school_access(user, s.school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    db.delete(s)
    db.commit()
    return None
