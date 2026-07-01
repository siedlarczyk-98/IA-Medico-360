"""Testes das funções puras de app/services/auth_service.py
(HMAC do Intercom e emissão de JWT — sem I/O de banco)."""

import hashlib
import hmac
from datetime import UTC

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.models.models import User
from app.services.auth_service import create_access_token, intercom_user_hash


def make_user(**kwargs) -> User:
    defaults = dict(email="medico@example.com", role="beta_user")
    defaults.update(kwargs)
    return User(**defaults)


# --- intercom_user_hash ---

def test_intercom_user_hash_sem_secret_retorna_none(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "intercom_identity_secret", "")
    user = make_user()
    assert intercom_user_hash(user) is None


def test_intercom_user_hash_e_hmac_sha256_do_user_id(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "intercom_identity_secret", "segredo-teste")
    user = make_user()

    result = intercom_user_hash(user)

    expected = hmac.new(
        b"segredo-teste",
        str(user.id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert result == expected


def test_intercom_user_hash_e_deterministico(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "intercom_identity_secret", "segredo-teste")
    user = make_user()
    assert intercom_user_hash(user) == intercom_user_hash(user)


# --- create_access_token ---

def test_create_access_token_contem_claims_esperadas():
    user = make_user(role="admin")
    settings = get_settings()

    token = create_access_token(user)

    payload = pyjwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == str(user.id)
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_create_access_token_expira_conforme_config():
    user = make_user()
    settings = get_settings()

    token = create_access_token(user)
    payload = pyjwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

    from datetime import datetime

    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    now = datetime.now(UTC)
    delta_minutes = (exp - now).total_seconds() / 60
    assert abs(delta_minutes - settings.jwt_access_token_expire_minutes) < 1


def test_create_access_token_rejeita_secret_errado():
    user = make_user()
    token = create_access_token(user)

    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(token, "secret-errado", algorithms=["HS256"])
