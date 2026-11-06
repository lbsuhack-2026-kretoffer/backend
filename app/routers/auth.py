from fastapi import APIRouter, HTTPException, Response, status

from ..auth_service import authenticate_user
from ..config import settings
from ..deps import DB, CurrentUser
from ..models import School, User
from ..schemas import LoginInput, UserOut
from ..security import encode_session, sign_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


def user_to_out(user: User, db) -> UserOut:
    school = db.get(School, user.school_id) if user.school_id else None
    return UserOut(
        id=user.id,
        fullName=user.full_name,
        email=user.email,
        role=user.role,
        schoolId=user.school_id,
        schoolName=school.name if school else None,
        position=user.position,
        avatarUrl=user.avatar_url,
    )


@router.post("/login", response_model=UserOut)
def login(data: LoginInput, db: DB, response: Response):
    user = authenticate_user(db, data.login, data.password)
    if not user:
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
