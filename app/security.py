import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256

from .config import settings

# ---------- Пароли: pbkdf2_sha256, как требует api (3).md, п.2 ----------


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        settings.secret_key.encode("utf-8"),
        100_000,
    ).hex()


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    expected = hash_password(plain_password)
    return hmac.compare_digest(expected, password_hash)


# Обратная совместимость: в старом коде использовалось имя get_password_hash
get_password_hash = hash_password


# ---------- Сессии: HMAC-подпись + itsdangerous-cookie ----------


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
