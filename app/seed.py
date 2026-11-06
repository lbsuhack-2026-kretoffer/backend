from sqlalchemy.orm import Session

from .config import settings
from .models import User
from .security import hash_password


def seed_superadmin(db: Session) -> None:
    if db.query(User).filter(User.role == "platform_admin").first():
        return
    db.add(
        User(
            full_name=settings.superadmin_name,
            email=settings.superadmin_email,
            password_hash=hash_password(settings.superadmin_password),
            role="platform_admin",
            position="Администратор платформы",
        )
    )
    db.commit()
    print(f"[seed] Супер-админ создан: {settings.superadmin_email}")
