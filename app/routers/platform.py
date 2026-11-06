from fastapi import APIRouter, Depends, HTTPException, Query, status  # noqa F401
from sqlalchemy import or_

from ..deps import DB, require_roles
from ..models import Attendance, School, SchoolAdmin, SchoolClass, Student, User
from ..schemas import (
    AccessToggle,
    SchoolAdminInput,
    SchoolInput,
    SchoolOut,
    SchoolPatch,
)
from ..security import hash_password
from ..utils import str_to_ids, today_tz

router = APIRouter(
    prefix="/platform",
    tags=["platform"],
    dependencies=[Depends(require_roles("platform_admin"))],
)


# ---------------------------------------------------------------------------
# Сериализация School → SchoolOut
# ---------------------------------------------------------------------------
def school_to_out(school: School, db) -> SchoolOut:
    admin_links = db.query(SchoolAdmin).filter(SchoolAdmin.school_id == school.id).all()
    admin_users = [db.get(User, link.user_id) for link in admin_links]
    admin_users = [u for u in admin_users if u]

    return SchoolOut(
        id=school.id,
        name=school.name,
        city=school.city,
        address=school.address,
        phone=school.phone,
        email=school.email,
        mealPlan=school.meal_plan,
        timezone=school.timezone,
        bufferPercent=school.buffer_percent,
        attendanceDeadline=school.attendance_deadline,
        accessEnabled=school.access_enabled,
        createdAt=school.created_at,
        integrations={"pos": school.integration_pos, "skud": school.integration_skud},
        adminIds=[u.id for u in admin_users],
        classesCount=db.query(SchoolClass).filter(SchoolClass.school_id == school.id).count(),
        studentsCount=db.query(Student).filter(Student.school_id == school.id).count(),
        teachersCount=db.query(User)
        .filter(User.school_id == school.id, User.role == "teacher")
        .count(),
        admins=[
            {
                "id": u.id,
                "fullName": u.full_name,
                "role": u.role,
                "position": u.position,
            }
            for u in admin_users
        ],
    )


# ---------------------------------------------------------------------------
# Сводная статистика платформы
# ---------------------------------------------------------------------------
@router.get("/stats")
def stats(db: DB):
    schools = db.query(School).all()
    total_students = db.query(Student).count()
    total_classes = db.query(SchoolClass).count()
    total_teachers = db.query(User).filter(User.role == "teacher").count()

    date = today_tz()
    present = absent = optouts = marked = 0

    for school in schools:
        class_ids = [
            c.id for c in db.query(SchoolClass).filter(SchoolClass.school_id == school.id).all()
        ]
        for cid in class_ids:
            rec = (
                db.query(Attendance)
                .filter(Attendance.class_id == cid, Attendance.date == date)
                .first()
            )
            total = db.query(Student).filter(Student.class_id == cid).count()
            opt = (
                db.query(Student)
                .filter(Student.class_id == cid, Student.meal_status == "opt_out")
                .count()
            )
            optouts += opt
            if rec:
                marked += 1
                absent_count = len(str_to_ids(rec.absent_ids))
                absent += absent_count
                present += max(total - opt - absent_count, 0)
            else:
                present += max(total - opt, 0)

    return {
        "schools": len(schools),
        "activeSchools": sum(1 for s in schools if s.access_enabled),
        "students": total_students,
        "classes": total_classes,
        "teachers": total_teachers,
        "attendance": {
            "present": present,
            "absent": absent,
            "optOuts": optouts,
            "markedClasses": marked,
            "totalClasses": total_classes,
            "date": date.isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Список школ с поиском и пагинацией
# ---------------------------------------------------------------------------
@router.get("/schools")
def list_schools(
    db: DB,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=200),
):
    q = db.query(School)
    if query:
        like = f"%{query.lower()}%"
        q = q.filter(
            or_(
                School.name.ilike(like),
                School.city.ilike(like),
                School.email.ilike(like),
            )
        )
    total = q.count()
    items = (
        q.order_by(School.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )
    return {
        "items": [school_to_out(s, db) for s in items],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ---------------------------------------------------------------------------
# Создание школы (+ опционально завуч)
# ---------------------------------------------------------------------------
@router.post("/schools", response_model=SchoolOut, status_code=201)
def create_school(data: SchoolInput, db: DB):
    school = School(
        name=data.name,
        city=data.city,
        address=data.address,
        phone=data.phone,
        email=data.email,
        meal_plan=data.mealPlan,
        timezone=data.timezone,
        buffer_percent=data.bufferPercent,
        attendance_deadline=data.attendanceDeadline,
        access_enabled=True,
    )
    db.add(school)
    db.flush()

    if data.adminEmail and data.adminPassword:
        existing = db.query(User).filter(User.email == data.adminEmail).first()
        if existing:
            # Переиспользуем существующего пользователя: назначаем завучем
            existing.role = "school_admin"
            existing.school_id = school.id
            existing.full_name = data.adminFullName or existing.full_name
            existing.password_hash = hash_password(data.adminPassword)
            admin_user = existing
        else:
            admin_user = User(
                full_name=data.adminFullName or "Завуч",
                email=data.adminEmail,
                password_hash=hash_password(data.adminPassword),
                role="school_admin",
                school_id=school.id,
                position="Завуч",
            )
            db.add(admin_user)
            db.flush()

        db.add(SchoolAdmin(school_id=school.id, user_id=admin_user.id))

    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


# ---------------------------------------------------------------------------
# Одна школа
# ---------------------------------------------------------------------------
@router.get("/schools/{school_id}", response_model=SchoolOut)
def get_school(school_id: str, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    return school_to_out(school, db)


# ---------------------------------------------------------------------------
# Патч школы
# ---------------------------------------------------------------------------
@router.patch("/schools/{school_id}", response_model=SchoolOut)
def patch_school(school_id: str, data: SchoolPatch, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")

    mapping = {
        "name": "name",
        "city": "city",
        "address": "address",
        "phone": "phone",
        "email": "email",
        "mealPlan": "meal_plan",
        "timezone": "timezone",
        "bufferPercent": "buffer_percent",
        "attendanceDeadline": "attendance_deadline",
    }
    payload = data.model_dump(exclude_unset=True)
    for key, attr in mapping.items():
        if key in payload and payload[key] is not None:
            setattr(school, attr, payload[key])

    if payload.get("integrations") is not None:
        school.integration_pos = payload["integrations"]["pos"]
        school.integration_skud = payload["integrations"]["skud"]

    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


# ---------------------------------------------------------------------------
# Назначение / создание завуча
# ---------------------------------------------------------------------------
@router.post("/schools/{school_id}/admins", response_model=SchoolOut)
def add_admin(school_id: str, data: SchoolAdminInput, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")

    user = db.query(User).filter(User.email == data.email).first()
    if user:
        # Обновляем существующего пользователя
        user.role = "school_admin"
        user.school_id = school.id
        user.full_name = data.fullName
        if data.password:
            user.password_hash = hash_password(data.password)
    else:
        user = User(
            full_name=data.fullName,
            email=data.email,
            password_hash=hash_password(data.password),
            role="school_admin",
            school_id=school.id,
            position="Завуч",
        )
        db.add(user)
        db.flush()

    exists = (
        db.query(SchoolAdmin)
        .filter(
            SchoolAdmin.school_id == school.id,
            SchoolAdmin.user_id == user.id,
        )
        .first()
    )
    if not exists:
        db.add(SchoolAdmin(school_id=school.id, user_id=user.id))

    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


# ---------------------------------------------------------------------------
# Отзыв завуча
# ---------------------------------------------------------------------------
@router.delete("/schools/{school_id}/admins/{user_id}", response_model=SchoolOut)
def remove_admin(school_id: str, user_id: str, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")

    user = db.get(User, user_id)
    if not user or user.school_id != school.id or user.role != "school_admin":
        raise HTTPException(404, "Завуч не найден")

    db.query(SchoolAdmin).filter(
        SchoolAdmin.school_id == school.id,
        SchoolAdmin.user_id == user.id,
    ).delete()
    db.delete(user)
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


# ---------------------------------------------------------------------------
# Блокировка / разблокировка доступа школы
# ---------------------------------------------------------------------------
@router.post("/schools/{school_id}/access", response_model=SchoolOut)
def set_access(school_id: str, data: AccessToggle, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    school.access_enabled = data.enabled
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)
