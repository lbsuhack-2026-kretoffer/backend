import uuid

from sqlalchemy.orm import Session

from .models import User
from .security import verify_password


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def authenticate_user(db: Session, login: str, password: str) -> User | None:
    login = login.strip()
    if _is_uuid(login):
        user = db.query(User).filter(User.id == login).first()
    else:
        user = db.query(User).filter(User.email == login).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user
