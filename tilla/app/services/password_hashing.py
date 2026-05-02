"""Password hashing for session login (bcrypt via passlib)."""

from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    if plain is None:
        raise ValueError("Password cannot be None")
    plain = str(plain).strip()
    if not plain:
        raise ValueError("Password cannot be empty")
    if len(plain.encode("utf-8")) > 72:
        raise ValueError("Password is too long for bcrypt; use <=72 bytes")
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False
