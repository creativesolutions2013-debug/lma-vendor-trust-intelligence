import pytest

from src.auth_context import get_current_principal
from src.authz import ROLE_ADMIN, ROLE_VIEWER


def clear_auth_env(monkeypatch):
    for name in (
        "AUTH_MODE",
        "DEV_USER_ROLE",
        "DEV_USER_SUBJECT",
        "DEV_USER_NAME",
        "DEV_USER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_development_mode_defaults_to_admin(monkeypatch):
    clear_auth_env(monkeypatch)

    principal = get_current_principal()

    assert principal.role == ROLE_ADMIN
    assert principal.subject == "local-demo-user"


def test_development_role_can_be_overridden(monkeypatch):
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("DEV_USER_ROLE", ROLE_VIEWER)
    monkeypatch.setenv("DEV_USER_NAME", "Read Only User")

    principal = get_current_principal()

    assert principal.role == ROLE_VIEWER
    assert principal.display_name == "Read Only User"


def test_invalid_development_role_is_rejected(monkeypatch):
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("DEV_USER_ROLE", "Superuser")

    with pytest.raises(ValueError, match="Unsupported DEV_USER_ROLE"):
        get_current_principal()


def test_production_mode_fails_closed(monkeypatch):
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "production")

    with pytest.raises(
        RuntimeError,
        match="Production authentication is not configured",
    ):
        get_current_principal()
