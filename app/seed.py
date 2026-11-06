from sqlalchemy.orm import Session

from .config import settings
from .models import User
from .security import hash_password


def seed_superadmin(db: Session) -> None:
    existing = db.query(User).filter(User.email == settings.superadmin_email).first()
    if existing:
        # Обновляем пароль на актуальный (важно после смены алгоритма хэширования)
        existing.password_hash = hash_password(settings.superadmin_password)
        existing.role = "platform_admin"
        db.commit()
        return

    db.add(
        User(
            id="u-platform",
            full_name=settings.superadmin_name,
            email=settings.superadmin_email,
            password_hash=hash_password(settings.superadmin_password),
            role="platform_admin",
            position="Администратор платформы",
        )
    )
    db.commit()
    print(
        f"[seed] Супер-админ создан: {settings.superadmin_email} / {settings.superadmin_password}"
    )
