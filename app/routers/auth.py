import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..config import settings
from ..deps import DB, CurrentUser, require_roles
from ..models import School, User as UserModel
from ..schemas import (
    ChangeLoginInput,
    ChangePasswordInput,
    LoginInput,
    PlatformAdminInput,
    UserOut,
)
from ..security import encode_session, sign_cookie, verify_password, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def user_to_out(user: UserModel, db) -> UserOut:
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


@router.post("/login", response_model=UserOut)
def login(data: LoginInput, db: DB, response: Response):
    login = data.login.strip()

    q = db.query(UserModel)
    if _is_uuid(login):
        q = q.filter((UserModel.email == login) | (UserModel.id == login))
    else:
        q = q.filter(UserModel.email == login)

    user = q.first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    if user.school_id:
        school = db.get(School, user.school_id)
        if school and not school.access_enabled and user.role != "platform_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ школы заблокирован")
    token = encode_session(user.id)
    response.set_cookie(
        key=settings.session_cookie,
        value=sign_cookie(token),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=60 * 60 * 24 * 7,
        path="/",
    )
    return user_to_out(user, db)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser, db: DB):
    return user_to_out(user, db)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.session_cookie, path="/")
    return Response(status_code=204)


@router.post("/platform-admins", response_model=UserOut)
def create_platform_admin(data: PlatformAdminInput, db: DB, user: UserModel = Depends(require_roles("platform_admin"))):
    if db.query(UserModel).filter(UserModel.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    user = UserModel(
        full_name=data.fullName,
        email=data.email,
        password_hash=hash_password(data.password),
        role="platform_admin",
        school_id=None,
        position="Администратор платформы",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_out(user, db)


@router.post("/me/change-login", response_model=UserOut)
def change_login(data: ChangeLoginInput, user: CurrentUser, db: DB):
    if not verify_password(data.currentPassword, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный текущий пароль")
    if data.newEmail == user.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый e-mail совпадает с текущим")
    if db.query(UserModel).filter(UserModel.email == data.newEmail).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    user.email = data.newEmail
    db.commit()
    db.refresh(user)
    return user_to_out(user, db)


@router.post("/me/change-password", status_code=204)
def change_password(data: ChangePasswordInput, user: CurrentUser, db: DB):
    if not verify_password(data.currentPassword, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный текущий пароль")
    if data.newPassword == data.currentPassword:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Новый пароль совпадает с текущим")
    user.password_hash = hash_password(data.newPassword)
    db.commit()
    return Response(status_code=204)
