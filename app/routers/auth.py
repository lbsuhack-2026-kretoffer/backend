from app import models
from app.auth import create_session_token
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.schemas import DemoUserOut, LoginInput, UserOut
from app.serializers import teacher_with_classes_out, user_out
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/demo-users", response_model=list[DemoUserOut])
def demo_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    result = []
    for u in users:
        base = user_out(db, u)
        if u.role == "teacher":
            base = teacher_with_classes_out(db, u)
        else:
            base["classes"] = []
        result.append(base)
    return result


@router.post("/login", response_model=UserOut)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = db.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    token = create_session_token(user.id)
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return user_out(db, user)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.session_cookie)
