from datetime import date

from app import models
from app.database import get_db
from app.deps import require_roles
from app.schemas import (
    AccessToggleInput,
    AddAdminInput,
    PlatformStatsOut,
    SchoolCreateInput,
    SchoolOut,
    SchoolPage,
    SchoolPatchInput,
)
from app.serializers import school_out
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/stats", response_model=PlatformStatsOut)
def stats(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    schools = db.query(models.School).all()
    students = db.query(models.Student).count()
    classes = db.query(models.SchoolClass).count()
    teachers = db.query(models.User).filter_by(role="teacher").count()

    today = date.today()
    total_students = 0
    opt_outs = 0
    absent = 0
    present = 0
    marked_classes = 0
    total_classes = classes

    for cls in db.query(models.SchoolClass).all():
        cls_students = db.query(models.Student).filter_by(class_id=cls.id).all()
        n_students = len(cls_students)
        n_opt = sum(1 for s in cls_students if s.meal_status == "optOut")
        regular_ids = {s.id for s in cls_students if s.meal_status == "regular"}
        att = db.query(models.AttendanceRecord).filter_by(class_id=cls.id, date=today).first()
        n_absent = len(set(att.absent_student_ids or []) & regular_ids) if att else 0
        if att:
            marked_classes += 1
        total_students += n_students
        opt_outs += n_opt
        absent += n_absent
        present += max(0, n_students - n_opt - n_absent)

    return {
        "schools": len(schools),
        "active_schools": len(schools),
        "students": students,
        "classes": classes,
        "teachers": teachers,
        "attendance": {
            "present": present,
            "absent": absent,
            "opt_outs": opt_outs,
            "marked_classes": marked_classes,
            "total_classes": total_classes,
            "date": today,
        },
    }


@router.get("/schools", response_model=SchoolPage)
def list_schools(
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    q = db.query(models.School)
    if query:
        like = f"%{query}%"
        q = q.filter((models.School.name.ilike(like)) | (models.School.city.ilike(like)))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [school_out(db, s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/schools", response_model=SchoolOut, status_code=201)
def create_school(
    payload: SchoolCreateInput,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    sid = f"school-{db.query(models.School).count() + 1}"
    school = models.School(
        id=sid,
        name=payload.name,
        city=payload.city,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
        meal_plan=payload.meal_plan,
        timezone=payload.timezone,
        buffer_percent=payload.buffer_percent,
        attendance_deadline=payload.attendance_deadline,
        created_at=date.today(),
    )
    db.add(school)
    db.flush()

    if payload.admin_email:
        existing = db.query(models.User).filter_by(email=payload.admin_email).first()
        if existing:
            existing.school_id = sid
            existing.role = "school_admin"
            admin = existing
        else:
            admin = models.User(
                id=f"u-{sid}",
                full_name=payload.admin_full_name or "Завуч",
                email=payload.admin_email,
                role="school_admin",
                school_id=sid,
                position="Завуч",
            )
            db.add(admin)
            db.flush()
        db.add(models.SchoolAdmin(school_id=sid, user_id=admin.id))

    db.commit()
    db.refresh(school)
    return school_out(db, school)


@router.get("/schools/{school_id}", response_model=SchoolOut)
def get_school(
    school_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    return school_out(db, s)


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def patch_school(
    school_id: str,
    payload: SchoolPatchInput,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
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


@router.post("/schools/{school_id}/admins", response_model=SchoolOut)
def add_admin(
    school_id: str,
    payload: AddAdminInput,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    user = db.query(models.User).filter_by(email=payload.email).first()
    if not user:
        user = models.User(
            id=f"u-{school_id}-{db.query(models.User).count() + 1}",
            full_name=payload.full_name,
            email=payload.email,
            role="school_admin",
            school_id=school_id,
            position="Завуч",
        )
        db.add(user)
        db.flush()
    link = db.query(models.SchoolAdmin).filter_by(school_id=school_id, user_id=user.id).first()
    if not link:
        db.add(models.SchoolAdmin(school_id=school_id, user_id=user.id))
    db.commit()
    return school_out(db, s)


@router.delete("/schools/{school_id}/admins/{user_id}", response_model=SchoolOut)
def remove_admin(
    school_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    db.query(models.SchoolAdmin).filter_by(school_id=school_id, user_id=user_id).delete()
    db.commit()
    return school_out(db, s)


@router.post("/schools/{school_id}/access", response_model=SchoolOut)
def toggle_access(
    school_id: str,
    payload: AccessToggleInput,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_roles("platform_admin")),
):
    s = db.get(models.School, school_id)
    if not s:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    s.access_enabled = payload.enabled
    db.commit()
    db.refresh(s)
    return school_out(db, s)
