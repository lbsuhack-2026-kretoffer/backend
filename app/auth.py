from app.config import settings
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_session_token(user_id: str) -> str:
    return _serializer.dumps({"uid": user_id})


def decode_session_token(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None
