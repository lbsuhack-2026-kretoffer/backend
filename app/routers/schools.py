from datetime import date

from app import models
from app.database import get_db
from app.deps import ensure_school_access, get_current_user, require_roles
from app.schemas import (
    AssignTeacherInput,
    ClassCreateInput,
    ClassOut,
    ClassPatchInput,
    SchoolOut,
    SchoolPatchInput,
    StudentCreateInput,
    StudentOut,
    StudentPatchInput,
    StudentWithClassOut,
    TeacherCreateInput,
    TeacherWithClassesOut,
)
from app.serializers import (
    class_out,
    school_out,
    student_out,
    student_with_class_out,
    teacher_with_classes_out,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(tags=["schools"])


@router.get("/schools/{school_id}", response_model=SchoolOut)
def get_school(
    school_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ensure_school_access(user, school_id)
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    return school_out(db, s)


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def patch_school(
    school_id: str,
    payload: SchoolPatchInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    ensure_school_access(user, school_id)
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    data = payload.model_dump(exclude_unset=True)
    if "integrations" in data and data["integrations"] is not None:
        s.integration_pos = bool(data["integrations"].get("pos"))
        s.integration_skud = bool(data["integrations"].get("skud"))
        del data["integrations"]
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return school_out(db, s)


# ---------- Classes ----------
@router.get("/schools/{school_id}/classes", response_model=list[ClassOut])
def list_classes(
    school_id: str,
    date: date | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ensure_school_access(user, school_id)
    classes = db.query(models.SchoolClass).filter_by(school_id=school_id).all()
    return [class_out(db, c, date) for c in classes]


@router.post("/schools/{school_id}/classes", response_model=ClassOut, status_code=201)
def create_class(
    school_id: str,
    payload: ClassCreateInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    ensure_school_access(user, school_id)
    if not db.get(models.School, school_id):
        raise HTTPException(status_code=404, detail="Школа не найдена")
    age_group = payload.age_group or _age_group_by_grade(payload.grade)
    cid = f"class-{school_id}-{payload.name.lower().replace(' ', '')}-{db.query(models.SchoolClass).count() + 1}"
    cls = models.SchoolClass(
        id=cid,
        school_id=school_id,
        name=payload.name,
        grade=payload.grade,
        age_group=age_group,
    )
    db.add(cls)
    if payload.teacher_id:
        db.add(models.ClassTeacher(class_id=cid, teacher_id=payload.teacher_id))
    db.commit()
    db.refresh(cls)
    return class_out(db, cls)


def _age_group_by_grade(grade: int) -> str:
    if grade <= 4:
        return "junior"
    if grade <= 9:
        return "middle"
    return "senior"


@router.get("/classes/{class_id}", response_model=ClassOut)
def get_class(
    class_id: str,
    date: date | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    return class_out(db, cls, date)


@router.patch("/classes/{class_id}", response_model=ClassOut)
def patch_class(
    class_id: str,
    payload: ClassPatchInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    data = payload.model_dump(exclude_unset=True)
    teacher_id = data.pop("teacher_id", None)
    for k, v in data.items():
        setattr(cls, k, v)
    if teacher_id is not None:
        db.query(models.ClassTeacher).filter_by(class_id=class_id).delete()
        db.add(models.ClassTeacher(class_id=class_id, teacher_id=teacher_id))
    db.commit()
    db.refresh(cls)
    return class_out(db, cls)


@router.delete("/classes/{class_id}", status_code=204)
def delete_class(
    class_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    db.query(models.ClassTeacher).filter_by(class_id=class_id).delete()
    db.query(models.Student).filter_by(class_id=class_id).delete()
    db.query(models.AttendanceRecord).filter_by(class_id=class_id).delete()
    db.delete(cls)
    db.commit()


@router.post("/classes/{class_id}/teacher", response_model=ClassOut)
def assign_teacher(
    class_id: str,
    payload: AssignTeacherInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    teacher = db.get(models.User, payload.teacher_id)
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=400, detail="Учитель не найден")
    exists = (
        db.query(models.ClassTeacher).filter_by(class_id=class_id, teacher_id=teacher.id).first()
    )
    if not exists:
        db.add(models.ClassTeacher(class_id=class_id, teacher_id=teacher.id))
        db.commit()
    return class_out(db, cls)


# ---------- Students ----------
@router.get("/classes/{class_id}/students", response_model=list[StudentOut])
def list_students(
    class_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    students = db.query(models.Student).filter_by(class_id=class_id).all()
    return [student_out(s) for s in students]


@router.post("/classes/{class_id}/students", response_model=StudentOut, status_code=201)
def create_student(
    class_id: str,
    payload: StudentCreateInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    ensure_school_access(user, cls.school_id)
    sid = f"s-{db.query(models.Student).count() + 1}"
    student = models.Student(
        id=sid,
        school_id=cls.school_id,
        class_id=class_id,
        full_name=payload.full_name,
        meal_status=payload.meal_status,
        age_group=cls.age_group,
        card_number=f"C-{db.query(models.Student).count() + 1:04d}",
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student_out(student)


@router.patch("/students/{student_id}", response_model=StudentOut)
def patch_student(
    student_id: str,
    payload: StudentPatchInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    ensure_school_access(user, student.school_id)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(student, k, v)
    db.commit()
    db.refresh(student)
    return student_out(student)


@router.delete("/students/{student_id}", status_code=204)
def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    ensure_school_access(user, student.school_id)
    db.query(models.AccessEvent).filter_by(student_id=student_id).delete()
    db.delete(student)
    db.commit()


@router.get("/schools/{school_id}/students", response_model=list[StudentWithClassOut])
def list_school_students(
    school_id: str,
    query: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ensure_school_access(user, school_id)
    q = db.query(models.Student).filter_by(school_id=school_id)
    if query:
        q = q.filter(models.Student.full_name.ilike(f"%{query}%"))
    return [student_with_class_out(db, s) for s in q.all()]


# ---------- Teachers ----------
@router.get("/schools/{school_id}/teachers", response_model=list[TeacherWithClassesOut])
def list_teachers(
    school_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    ensure_school_access(user, school_id)
    teachers = db.query(models.User).filter_by(school_id=school_id, role="teacher").all()
    return [teacher_with_classes_out(db, t) for t in teachers]


@router.post("/schools/{school_id}/teachers", response_model=TeacherWithClassesOut, status_code=201)
def create_teacher(
    school_id: str,
    payload: TeacherCreateInput,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_roles("school_admin")),
):
    ensure_school_access(user, school_id)
    if db.query(models.User).filter_by(email=payload.email).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким email уже существует")
    t = models.User(
        id=f"u-{school_id}-t{db.query(models.User).filter_by(school_id=school_id).count() + 1}",
        full_name=payload.full_name,
        email=payload.email,
        role="teacher",
        school_id=school_id,
        position=payload.position or "Учитель",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return teacher_with_classes_out(db, t)
