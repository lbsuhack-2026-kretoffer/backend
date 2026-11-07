from fastapi import APIRouter, HTTPException

from ..deps import DB, CurrentUser, ensure_school_access
from ..models import Attendance, CanteenKitchen, School, SchoolClass, Student, User
from ..schemas import ClassCreateWithStudentsInput, ClassPatch, SchoolOut, SchoolPatch
from ..utils import parse_date, str_to_ids
from .platform import school_to_out

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("/{school_id}", response_model=SchoolOut)
def get_school(school_id: str, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    return school_to_out(school, db)


@router.patch("/{school_id}", response_model=SchoolOut)
def patch_school(school_id: str, data: SchoolPatch, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
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
    for key, attr in mapping.items():
        if key in payload and payload[key] is not None:
            setattr(school, attr, payload[key])
    if payload.get("integrations"):
        school.integration_pos = payload["integrations"]["pos"]
        school.integration_skud = payload["integrations"]["skud"]
    db.commit()
    db.refresh(school)
    return school_to_out(school, db)


@router.get("/{school_id}/classes")
def list_classes(school_id: str, db: DB, user: CurrentUser, date_: str | None = None):
    ensure_school_access(user, school_id)
    target = parse_date(date_)
    classes = (
        db.query(SchoolClass)
        .filter(SchoolClass.school_id == school_id)
        .order_by(SchoolClass.grade, SchoolClass.name)
        .all()
    )
    result = []
    for c in classes:
        teachers = (
            db.query(User)
            .join(
                __import__("app.models", fromlist=["ClassTeacher"]).ClassTeacher,
                __import__("app.models", fromlist=["ClassTeacher"]).ClassTeacher.teacher_id
                == User.id,
            )
            .filter(
                __import__("app.models", fromlist=["ClassTeacher"]).ClassTeacher.class_id == c.id
            )
            .all()
        )
        students_count = db.query(Student).filter(Student.class_id == c.id).count()
        opt = (
            db.query(Student)
            .filter(Student.class_id == c.id, Student.meal_status == "opt_out")
            .count()
        )
        rec = (
            db.query(Attendance)
            .filter(Attendance.class_id == c.id, Attendance.date == target)
            .first()
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
        result.append(
            {
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
        )
    return result


@router.post("/{school_id}/classes", status_code=201)
def create_class(
    school_id: str,
    data: ClassCreateWithStudentsInput,
    db: DB,
    user: CurrentUser,
):
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")

    grade = data.grade
    letter = data.letter.strip().upper()
    class_name = f"{grade}{letter}"
    age_group = "junior" if grade <= 4 else "middle" if grade <= 9 else "senior"

    klass = SchoolClass(
        school_id=school_id,
        name=class_name,
        grade=grade,
        age_group=age_group,
    )
    db.add(klass)
    db.flush()

    # Создаём учеников по списку ФИО
    for full_name in data.studentNames:
        s = Student(
            school_id=school_id,
            class_id=klass.id,
            full_name=full_name.strip(),
            meal_status="regular",
            age_group=age_group,
        )
        db.add(s)

    db.commit()
    db.refresh(klass)

    return {
        "id": klass.id,
        "schoolId": klass.school_id,
        "name": klass.name,
        "grade": klass.grade,
        "ageGroup": klass.age_group,
        "teacherIds": [],
        "teacherNames": [],
        "studentsCount": len(data.studentNames),
        "optOutsCount": 0,
        "attendance": None,
    }


@router.get("/{school_id}/teachers")
def list_teachers(school_id: str, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    from ..models import ClassTeacher

    teachers = db.query(User).filter(User.school_id == school_id, User.role == "teacher").all()
    result = []
    for t in teachers:
        classes = (
            db.query(SchoolClass)
            .join(ClassTeacher, ClassTeacher.class_id == SchoolClass.id)
            .filter(ClassTeacher.teacher_id == t.id)
            .all()
        )
        result.append(
            {
                "id": t.id,
                "fullName": t.full_name,
                "email": t.email,
                "role": t.role,
                "schoolId": t.school_id,
                "position": t.position,
                "classes": [{"id": c.id, "name": c.name, "grade": c.grade} for c in classes],
            }
        )
    return result


@router.post("/{school_id}/teachers", status_code=201)
def create_teacher(school_id: str, data: dict, db: DB, user: CurrentUser):
    ensure_school_access(user, school_id)
    if user.role not in ("platform_admin", "school_admin"):
        raise HTTPException(403, "Недостаточно прав")
    from ..security import hash_password

    email = data["email"]
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "Пользователь с таким e-mail уже существует")
    role = data.get("role", "teacher")
    if role not in ("teacher", "guard"):
        raise HTTPException(400, "Недопустимая роль")
    t = User(
        full_name=data["fullName"],
        email=email,
        password_hash=hash_password(data["password"]),
        role=role,
        school_id=school_id,
        position=data.get("position"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "id": t.id,
        "fullName": t.full_name,
        "email": t.email,
        "role": t.role,
        "schoolId": t.school_id,
        "position": t.position,
        "classes": [],
    }


@router.get("/{school_id}/students")
def search_students(
    school_id: str,
    db: DB,
    user: CurrentUser,
    query: str | None = None,
    search_by: str = "surname",
):
    ensure_school_access(user, school_id)
    q = db.query(Student).filter(Student.school_id == school_id)
    if query:
        needle = query.strip().lower()
        if search_by == "firstname":
            # эвристика: ФИО хранится как "Фамилия Имя Отчество"
            q = q.filter(Student.full_name.ilike(f"% {needle}%"))
        elif search_by == "middlename":
            q = q.filter(Student.full_name.ilike(f"% % {needle}%"))
        else:
            q = q.filter(Student.full_name.ilike(f"{needle}%"))
    students = q.order_by(Student.full_name).limit(500).all()
    cls_names = {
        c.id: c.name for c in db.query(SchoolClass).filter(SchoolClass.school_id == school_id).all()
    }
    return [
        {
            "id": s.id,
            "schoolId": s.school_id,
            "classId": s.class_id,
            "fullName": s.full_name,
            "mealStatus": s.meal_status,
            "ageGroup": s.age_group,
            "cardNumber": s.card_number,
            "className": cls_names.get(s.class_id),
        }
        for s in students
    ]


@router.get("/{school_id}/attendance/summary")
def attendance_summary(school_id: str, db: DB, user: CurrentUser, date: str | None = None):
    ensure_school_access(user, school_id)
    target = parse_date(date)
    classes = db.query(SchoolClass).filter(SchoolClass.school_id == school_id).all()
    total_students = present = absent = opt = marked = 0
    for c in classes:
        st = db.query(Student).filter(Student.class_id == c.id).all()
        total_students += len(st)
        opt_here = sum(1 for s in st if s.meal_status == "opt_out")
        opt += opt_here
        rec = (
            db.query(Attendance)
            .filter(Attendance.class_id == c.id, Attendance.date == target)
            .first()
        )
        if rec:
            marked += 1
            a = len(str_to_ids(rec.absent_ids))
            absent += a
            present += max(len(st) - opt_here - a, 0)
        else:
            present += max(len(st) - opt_here, 0)
    return {
        "date": target.isoformat(),
        "totalStudents": total_students,
        "present": present,
        "absent": absent,
        "optOuts": opt,
        "markedClasses": marked,
        "totalClasses": len(classes),
    }


@router.get("/{school_id}/kitchen")
def get_school_kitchen(school_id: str, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(404, "Школа не найдена")
    ensure_school_access(user, school_id)
    kitchen = (
        db.query(CanteenKitchen)
        .filter(CanteenKitchen.district == school.district)
        .first()
    )
    if not kitchen:
        return {"id": None, "name": None, "district": school.district}
    return {"id": kitchen.id, "name": kitchen.name, "district": kitchen.district}
