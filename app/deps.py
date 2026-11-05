from app import models
from app.auth import decode_session_token
from app.config import settings
from app.database import get_db
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session


def get_current_user(
    x_demo_user: str | None = Header(None, alias="X-Demo-User"),
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie),
    db: Session = Depends(get_db),
) -> models.User:
    user_id = x_demo_user
    if not user_id and session_cookie:
        user_id = decode_session_token(session_cookie)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Нет сессии")
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден"
        )
    return user


def require_roles(*roles: str):
    def dep(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user

    return dep


def ensure_school_access(user: models.User, school_id: str) -> None:
    if user.role == "platform_admin":
        return
    if user.school_id != school_id:
        raise HTTPException(status_code=403, detail="Доступ к другой школе запрещён")


def get_school_or_404(db: Session, school_id: str) -> models.School:
    school = db.get(models.School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")
    return school


def get_class_or_404(db: Session, class_id: str) -> models.SchoolClass:
    cls = db.get(models.SchoolClass, class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Класс не найден")
    return cls


def teacher_class_ids(db: Session, teacher_id: str) -> set[str]:
    rows = db.query(models.ClassTeacher).filter_by(teacher_id=teacher_id).all()
    return {r.class_id for r in rows}
