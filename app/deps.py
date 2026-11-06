from app import models
from app.auth import decode_session_token
from app.config import settings
from app.database import get_db
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session


def get_current_user(
    session_cookie: str | None = Cookie(None, alias=settings.session_cookie),
    db: Session = Depends(get_db),
) -> models.User:
    user_id = decode_session_token(session_cookie) if session_cookie else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Нет сессии")
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
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


def teacher_class_ids(db: Session, teacher_id: str) -> set[str]:
    rows = db.query(models.ClassTeacher).filter_by(teacher_id=teacher_id).all()
    return {r.class_id for r in rows}
