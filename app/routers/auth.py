from app import models
from app.auth import create_session_token, verify_password
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.schemas import LoginInput, UserOut
from app.serializers import user_out
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)):
    user = (
        db.query(models.User)
        .filter((models.User.email == payload.login) | (models.User.id == payload.login))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

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
