from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import DB, CurrentUser, require_roles, ensure_school_access
from ..models import Attendance, CanteenKitchen, CanteenMenuItem, School, SchoolClass, Student, User
from ..schemas import (
    AccessToggle,
    KitchenInput,
    KitchenOut,
    KitchenUserInput,
    MenuItemInput,
    MenuItemOut,
    KitchenPatch,
    SchoolAdminInput,
    SchoolInput,
    SchoolKitchenPatch,
    SchoolOut,
    SchoolPatch,
    UserOut,
)
from ..security import hash_password
from ..utils import str_to_ids, today_tz

router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(require_roles("platform_admin"))]
)


def user_to_out(user: User, db) -> UserOut:
    school = db.get(School, user.school_id) if user.school_id else None
    return UserOut(
        id=user.id,
        fullName=user.full_name,
        email=user.email,
        role=user.role,
        schoolId=user.school_id,
        schoolName=school.name if school else None,
        district=user.district,
        position=user.position,
        avatarUrl=user.avatar_url,
    )


def school_to_out(school: School, db) -> SchoolOut:
    admins = db.query(User).filter(User.school_id == school.id, User.role == "school_admin").all()
    kitchen = None
    if school.kitchen_id:
        kitchen = db.query(CanteenKitchen).filter(CanteenKitchen.id == school.kitchen_id).first()
    return SchoolOut(
        id=school.id,
        name=school.name,
        city=school.city,
        district=school.district,
        address=school.address,
        phone=school.phone,
        email=school.email,
        mealPlan=school.meal_plan,
        bufferPercent=school.buffer_percent,
        attendanceDeadline=school.attendance_deadline,
        accessEnabled=school.access_enabled,
        createdAt=school.created_at,
        integrations={"pos": school.integration_pos, "skud": school.integration_skud},
        adminIds=[a.id for a in admins],
        classesCount=db.query(SchoolClass).filter(SchoolClass.school_id == school.id).count(),
        studentsCount=db.query(Student).filter(Student.school_id == school.id).count(),
        teachersCount=db.query(User)
        .filter(User.school_id == school.id, User.role == "teacher")
        .count(),
        admins=[
            {"id": a.id, "fullName": a.full_name, "role": a.role, "position": a.position}
            for a in admins
        ],
        kitchenId=kitchen.id if kitchen else None,
        kitchenName=kitchen.name if kitchen else None,
    )


@router.get("/stats")
def stats(db: DB):
    schools = db.query(School).all()
    total_students = db.query(Student).count()
    total_classes = db.query(SchoolClass).count()
    total_teachers = db.query(User).filter(User.role == "teacher").count()
    date = today_tz()
    present = absent = optouts = marked = 0
    for school in schools:
        cls_ids = [
            c.id for c in db.query(SchoolClass).filter(SchoolClass.school_id == school.id).all()
        ]
        for cid in cls_ids:
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


@router.get("/schools")
def list_schools(
    db: DB,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    q = db.query(School)
    if query:
        like = f"%{query.lower()}%"
        q = q.filter(
            (School.name.ilike(like)) | (School.city.ilike(like)) | (School.email.ilike(like))
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


@router.post("/schools", response_model=SchoolOut, status_code=201)
def create_school(data: SchoolInput, db: DB):
    school = School(
        name=data.name,
        city=data.city,
        address=data.address,
        phone=data.phone,
        email=data.email,
        meal_plan=data.mealPlan,
        buffer_percent=data.bufferPercent,
        attendance_deadline=data.attendanceDeadline,
        access_enabled=True,
        district=data.district,
    )
    db.add(school)
    db.flush()
    # Автоподключение к КШП того же района
    kitchen = db.query(CanteenKitchen).filter(CanteenKitchen.district == data.district).first()
    if kitchen:
        school.kitchen_id = kitchen.id
    if data.adminEmail and data.adminPassword:
        existing = db.query(User).filter(User.email == data.adminEmail).first()
        if existing:
            db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует"
            )
        db.add(
            User(
                full_name=data.adminFullName or "Завуч",
                email=data.adminEmail,
                password_hash=hash_password(data.adminPassword),
                role="school_admin",
                school_id=school.id,
                position="Завуч",
            )
        )
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.get("/schools/{school_id}", response_model=SchoolOut)
def get_school(school_id: str, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    return school_to_out(school, db)


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def patch_school(school_id: str, data: SchoolPatch, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    mapping = {
        "name": "name",
        "city": "city",
        "district": "district",
        "address": "address",
        "phone": "phone",
        "email": "email",
        "mealPlan": "meal_plan",
        "bufferPercent": "buffer_percent",
        "attendanceDeadline": "attendance_deadline",
    }
    payload = data.model_dump(exclude_unset=True)
    original_district = school.district
    for key, attr in mapping.items():
        if key in payload and payload[key] is not None:
            setattr(school, attr, payload[key])
    if "integrations" in payload and payload["integrations"] is not None:
        integ = payload["integrations"]
        school.integration_pos = bool(integ.get("pos", school.integration_pos))
        school.integration_skud = bool(integ.get("skud", school.integration_skud))
    db.flush()
    # Если район школы изменился — перепривязываем её к КШП нового района
    if (
        "district" in payload
        and payload["district"] is not None
        and payload["district"] != original_district
    ):
        kitchen = (
            db.query(CanteenKitchen)
            .filter(CanteenKitchen.district == school.district)
            .first()
        )
        school.kitchen_id = kitchen.id if kitchen else None
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.delete("/schools/{school_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_school(school_id: str, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    db.delete(school)
    db.commit()
    return None


@router.post("/schools/{school_id}/admins", response_model=SchoolOut)
def add_admin(school_id: str, data: SchoolAdminInput, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    db.add(
        User(
            full_name=data.fullName,
            email=data.email,
            password_hash=hash_password(data.password),
            role="school_admin",
            school_id=school.id,
            position="Завуч",
        )
    )
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.delete("/schools/{school_id}/admins/{user_id}", response_model=SchoolOut)
def remove_admin(school_id: str, user_id: str, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    user = db.get(User, user_id)
    if not user or user.school_id != school.id or user.role != "school_admin":
        raise HTTPException(404, "Завуч не найден")
    db.delete(user)
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.post("/schools/{school_id}/access", response_model=SchoolOut)
def set_access(school_id: str, data: AccessToggle, db: DB):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    school.access_enabled = data.enabled
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


# ---- КШП района (комбинат питания)
@router.get("/kitchens", response_model=list[KitchenOut])
def list_kitchens(db: DB):
    kitchens = db.query(CanteenKitchen).all()
    return [{"id": k.id, "name": k.name, "district": k.district} for k in kitchens]


@router.get("/kitchens/{kitchen_id}/user", response_model=UserOut | None)
def get_kitchen_user(kitchen_id: str, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    user = (
        db.query(User)
        .filter(User.role == "canteen", User.district == kitchen.district)
        .first()
    )
    if not user:
        return None
    return user_to_out(user, db)


@router.post("/kitchens", response_model=KitchenOut, status_code=201)
def create_kitchen(data: KitchenInput, db: DB):
    kitchen = CanteenKitchen(name=data.name, district=data.district)
    db.add(kitchen)
    db.flush()

    # Автоподключение всех школ этого района к новому КШП
    schools = db.query(School).filter(School.district == data.district).all()
    for s in schools:
        s.kitchen_id = kitchen.id

    # Создаём пользователя КШП (логин/пароль общего аккаунта)
    if data.email and data.fullName and data.password:
        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Пользователь с таким e-mail уже существует",
            )
        user_kitchen = User(
            full_name=data.fullName,
            email=data.email,
            password_hash=hash_password(data.password),
            role="canteen",
            school_id=None,
            position="Сотрудник комбината питания",
            district=data.district,
        )
        db.add(user_kitchen)
        db.flush()
        # Привязываем пользователя КШП к первой школе своего района, чтобы у него был school_id
        first_school = db.query(School).filter(School.district == data.district).first()
        if first_school:
            user_kitchen.school_id = first_school.id

    db.commit()
    db.refresh(kitchen)
    return {"id": kitchen.id, "name": kitchen.name, "district": kitchen.district}


@router.delete("/kitchens/{kitchen_id}", status_code=204)
def delete_kitchen(kitchen_id: str, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    db.delete(kitchen)
    db.commit()
    return None


@router.patch("/kitchens/{kitchen_id}", response_model=KitchenOut)
def patch_kitchen(kitchen_id: str, data: KitchenPatch, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    payload = data.model_dump(exclude_unset=True)
    original_district = kitchen.district
    if "name" in payload and payload["name"] is not None:
        kitchen.name = payload["name"]
    if "district" in payload and payload["district"] is not None:
        kitchen.district = payload["district"]
    # Если район КШП изменился — перепривязываем школы:
    # отвязываем школы, которые остались в старом районе, и привязываем
    # школы нового района, у которых ещё нет КШП
    if (
        "district" in payload
        and payload["district"] is not None
        and payload["district"] != original_district
    ):
        new_district = kitchen.district
        db.query(School).filter(
            School.kitchen_id == kitchen.id,
            School.district != new_district,
        ).update({School.kitchen_id: None}, synchronize_session=False)
        for s in (
            db.query(School)
            .filter(School.district == new_district, School.kitchen_id.is_(None))
            .all()
        ):
            s.kitchen_id = kitchen.id
    # Обновляем общий аккаунт сотрудника КШП этого района (email, ФИО, пароль)
    user = (
        db.query(User)
        .filter(User.role == "canteen", User.district == kitchen.district)
        .first()
    )
    if user:
        if "email" in payload and payload["email"] is not None:
            user.email = payload["email"]
        if "fullName" in payload and payload["fullName"] is not None:
            user.full_name = payload["fullName"]
        if "password" in payload and payload["password"] is not None:
            user.password_hash = hash_password(payload["password"])
    db.commit()
    db.refresh(kitchen)
    return {"id": kitchen.id, "name": kitchen.name, "district": kitchen.district}


@router.post("/kitchens/{kitchen_id}/link-schools", response_model=dict)
def link_district_schools(kitchen_id: str, db: DB):
    """Привязать все школы района этого КШП, у которых ещё нет КШП."""
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    schools = (
        db.query(School)
        .filter(School.district == kitchen.district, School.kitchen_id.is_(None))
        .all()
    )
    for s in schools:
        s.kitchen_id = kitchen.id
    db.commit()
    return {"linked": len(schools), "district": kitchen.district}


@router.post("/kitchens/{kitchen_id}/users", response_model=UserOut, status_code=201)
def create_kitchen_user(kitchen_id: str, data: KitchenUserInput, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    user = User(
        full_name=data.fullName,
        email=data.email,
        password_hash=hash_password(data.password),
        role="canteen",
        school_id=None,
        position="Сотрудник комбината питания",
        district=kitchen.district,
    )
    db.add(user)
    db.flush()
    # Привязываем пользователя КШП к первой школе своего района
    first_school = db.query(School).filter(School.district == kitchen.district).first()
    if first_school:
        user.school_id = first_school.id
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "fullName": user.full_name,
        "email": user.email,
        "role": user.role,
        "schoolId": user.school_id,
        "schoolName": None,
        "district": user.district,
        "position": user.position,
        "avatarUrl": user.avatar_url,
    }


@router.get("/kitchens/{kitchen_id}/schools", response_model=list[SchoolOut])
def list_kitchen_schools(kitchen_id: str, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    schools = db.query(School).filter(School.kitchen_id == kitchen_id).all()
    return [school_to_out(s, db) for s in schools]


@router.get("/kitchens/{kitchen_id}/available-schools", response_model=list[SchoolOut])
def list_available_schools(kitchen_id: str, db: DB):
    kitchen = db.get(CanteenKitchen, kitchen_id)
    if not kitchen:
        raise HTTPException(404, "КШП не найдено")
    schools = (
        db.query(School)
        .filter(School.district == kitchen.district, School.kitchen_id.is_(None))
        .all()
    )
    return [school_to_out(s, db) for s in schools]


@router.patch("/schools/{school_id}/kitchen", response_model=SchoolOut)
def set_school_kitchen(school_id: str, data: SchoolKitchenPatch, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    if data.kitchenId is not None:
        kitchen = db.get(CanteenKitchen, data.kitchenId)
        if not kitchen:
            raise HTTPException(404, "КШП не найдено")
    school.kitchen_id = data.kitchenId
    db.flush()
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.get("/kitchens/{kitchen_id}/menu", response_model=list[MenuItemOut])
def list_kitchen_menu(kitchen_id: str, db: DB):
    items = db.query(CanteenMenuItem).filter(CanteenMenuItem.kitchen_id == kitchen_id).all()
    return [
        {"id": i.id, "kitchen_id": i.kitchen_id, "name": i.name, "price": i.price}
        for i in items
    ]


@router.post("/kitchens/{kitchen_id}/menu", response_model=MenuItemOut, status_code=201)
def create_menu_item(kitchen_id: str, data: MenuItemInput, db: DB):
    item = CanteenMenuItem(kitchen_id=kitchen_id, name=data.name, price=data.price)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "kitchen_id": item.kitchen_id, "name": item.name, "price": item.price}


@router.get("/kitchens/{kitchen_id}/menu/day", response_model=list[MenuItemOut])
def get_kitchen_menu_day(kitchen_id: str, db: DB, date: str = None):
    from datetime import date as date_cls
    target = date_cls.fromisoformat(date) if date else date_cls.today()
    # Для MVP возвращаем все активные блюда кухни (в реальности можно привязать к дате)
    items = db.query(CanteenMenuItem).filter(CanteenMenuItem.kitchen_id == kitchen_id).all()
    return [
        {"id": i.id, "kitchen_id": i.kitchen_id, "name": i.name, "price": i.price}
        for i in items
    ]
