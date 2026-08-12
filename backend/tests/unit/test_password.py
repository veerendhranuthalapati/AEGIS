"""Password hashing tests."""
import pytest

from app.auth.password import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("CorrectHorseBatteryStaple")
    assert hashed.startswith("$2")
    assert verify_password("CorrectHorseBatteryStaple", hashed)


def test_wrong_password_rejected():
    hashed = hash_password("right-password")
    assert not verify_password("wrong-password", hashed)


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_garbage_hash_returns_false():
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_hashes_are_unique_salts():
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
