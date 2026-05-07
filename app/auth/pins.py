"""PIN hashing and lockout helpers.

PINs are 4–6 digit numeric strings. We use argon2 (memory-hard) rather than bcrypt
even though the input space is tiny — the lockout below is the real defense; the
hash only matters if the DB leaks. Three failures triggers a 60-second cooldown.
"""

from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.models import User

_PIN_MIN_LEN = 4
_PIN_MAX_LEN = 6
_LOCKOUT_THRESHOLD = 3
_LOCKOUT_SECONDS = 60

_hasher = PasswordHasher()


def is_valid_pin(pin: str) -> bool:
    return pin.isdigit() and _PIN_MIN_LEN <= len(pin) <= _PIN_MAX_LEN


def hash_pin(pin: str) -> str:
    return _hasher.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return _hasher.verify(pin_hash, pin)
    except VerifyMismatchError:
        return False


def is_locked(user: User, now: datetime | None = None) -> bool:
    if user.pin_locked_until is None:
        return False
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return user.pin_locked_until > now


def lockout_seconds_remaining(user: User, now: datetime | None = None) -> int:
    if user.pin_locked_until is None:
        return 0
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (user.pin_locked_until - now).total_seconds()
    return max(0, int(delta))


def record_failure(user: User, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    user.failed_pin_count = (user.failed_pin_count or 0) + 1
    if user.failed_pin_count >= _LOCKOUT_THRESHOLD:
        user.pin_locked_until = now + timedelta(seconds=_LOCKOUT_SECONDS)
        user.failed_pin_count = 0


def record_success(user: User) -> None:
    user.failed_pin_count = 0
    user.pin_locked_until = None
