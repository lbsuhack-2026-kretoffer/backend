from app import models
from sqlalchemy.orm import Session


def user_out(db: Session, u: models.User) -> dict:
    school_name = None
    if u.school_id:
        s = db.get(models.School, u.school_id)
        school_name = s.name if s else None
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
        "school_id": u.school_id,
        "school_name": school_name,
        "position": u.position,
        "avatar_url": u.avatar_url,
    }


def school_out(db: Session, s: models.School) -> dict:
    admins = (
        db.query(models.User)
        .join(models.SchoolAdmin, models.SchoolAdmin.user_id == models.User.id)
        .filter(models.SchoolAdmin.school_id == s.id)
        .all()
    )
    return {
        "id": s.id,
        "name": s.name,
        "city": s.city,
        "address": s.address,
        "phone": s.phone,
        "email": s.email,
        "meal_plan": s.meal_plan,
        "timezone": s.timezone,
        "buffer_percent": s.buffer_percent,
        "attendance_deadline": s.attendance_deadline,
        "access_enabled": s.access_enabled,
        "created_at": s.created_at,
        "integrations": {"pos": s.integration_pos, "skud": s.integration_skud},
        "admin_ids": [a.id for a in admins],
        "classes_count": db.query(models.SchoolClass).filter_by(school_id=s.id).count(),
        "students_count": db.query(models.Student).filter_by(school_id=s.id).count(),
        "teachers_count": db.query(models.User).filter_by(school_id=s.id, role="teacher").count(),
        "admins": [
            {"id": a.id, "full_name": a.full_name, "role": a.role, "position": a.position}
            for a in admins
        ],
    }


def class_out(db: Session, cls: models.SchoolClass, date_q=None) -> dict:
    teachers = (
        db.query(models.User)
        .join(models.ClassTeacher, models.ClassTeacher.teacher_id == models.User.id)
        .filter(models.ClassTeacher.class_id == cls.id)
        .all()
    )
    students = db.query(models.Student).filter_by(class_id=cls.id).all()
    attendance_block = None
    if date_q:
        att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=date_q).first()
        if att:
            absent = len(
                set(att.absent_student_ids or [])
                & {s.id for s in students if s.meal_status == "regular"}
            )
            sub = db.get(models.User, att.submitted_by_id)
            attendance_block = {
                "status": "marked",
                "absent_count": absent,
                "submitted_at": att.submitted_at.strftime("%H:%M"),
                "submitted_by_name": sub.full_name if sub else None,
            }
        else:
            attendance_block = {
                "status": "pending",
                "absent_count": 0,
                "submitted_at": None,
                "submitted_by_name": None,
            }
    return {
        "id": cls.id,
        "school_id": cls.school_id,
        "name": cls.name,
        "grade": cls.grade,
        "age_group": cls.age_group,
        "teacher_ids": [t.id for t in teachers],
        "teacher_names": [t.full_name for t in teachers],
        "students_count": len(students),
        "opt_outs_count": sum(1 for s in students if s.meal_status == "optOut"),
        "attendance": attendance_block,
    }


def student_out(s: models.Student) -> dict:
    return {
        "id": s.id,
        "school_id": s.school_id,
        "class_id": s.class_id,
        "full_name": s.full_name,
        "meal_status": s.meal_status,
        "age_group": s.age_group,
        "card_number": s.card_number,
    }


def student_with_class_out(db: Session, s: models.Student) -> dict:
    out = student_out(s)
    cls = db.get(models.SchoolClass, s.class_id)
    out["class_name"] = cls.name if cls else ""
    return out


def teacher_with_classes_out(db: Session, u: models.User) -> dict:
    out = user_out(db, u)
    rows = db.query(models.ClassTeacher).filter_by(teacher_id=u.id).all()
    out["classes"] = [
        {"id": c.id, "name": c.name}
        for c in [db.get(models.SchoolClass, r.class_id) for r in rows]
        if c
    ]
    return out
