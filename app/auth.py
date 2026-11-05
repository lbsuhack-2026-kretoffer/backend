from app.config import settings
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def create_session_token(user_id: str) -> str:
    return _serializer.dumps({"uid": user_id})


def decode_session_token(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
        return data.get("uid")
    except (BadSignature, SignatureExpired):
        return None
