from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import School, User
from .security import decode_session, unsign_cookie


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DB,
    sbp_session: Annotated[str | None, Cookie(alias=settings.session_cookie)] = None,
) -> User:
    if not sbp_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Не авторизован")
    token = unsign_cookie(sbp_session)
    uid = decode_session(token) if token else None
    if not uid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    if user.school_id:
        school = db.get(School, user.school_id)
        if school and not school.access_enabled and user.role != "platform_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ школы заблокирован")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    def _checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return _checker


def ensure_school_access(user: User, school_id: str):
    if user.role == "platform_admin":
        return
    if user.school_id != school_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ к чужой школе запрещён")
