import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256

import bcrypt

from .config import settings


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


def _sign(payload: bytes) -> str:
    sig = hmac.new(settings.secret_key.encode(), payload, sha256).digest()
    return urlsafe_b64encode(sig).decode().rstrip("=")


def encode_session(user_id: str) -> str:
    payload = json.dumps({"sub": user_id}, separators=(",", ":")).encode()
    body = urlsafe_b64encode(payload).decode().rstrip("=")
    return f"{body}.{_sign(payload)}"


def decode_session(token: str) -> str | None:
    try:
        body, sig = token.split(".")
        padding = "=" * (-len(body) % 4)
        payload = urlsafe_b64decode(body + padding)
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        return json.loads(payload).get("sub")
    except Exception:
        return None


def sign_cookie(token: str) -> str:
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(settings.secret_key).dumps(token)


def unsign_cookie(value: str, max_age: int = 60 * 60 * 24 * 7) -> str | None:
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    try:
        return URLSafeTimedSerializer(settings.secret_key).loads(value, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
