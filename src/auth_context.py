import os
from dataclasses import dataclass

from src.authz import Principal, ROLE_ADMIN, VALID_ROLES


AUTH_MODE_DEVELOPMENT = "development"
AUTH_MODE_PRODUCTION = "production"


@dataclass(frozen=True)
class StartupContext:
    """Startup configuration and demo principal, not verified production identity."""

    mode: str
    principal: Principal

    @property
    def development_demo_seed_allowed(self) -> bool:
        # Keep this mode check even when a future trusted IdP is implemented.
        return self.mode == AUTH_MODE_DEVELOPMENT


def get_auth_mode() -> str:
    """Resolve an explicit mode decision without touching storage or a database."""
    mode = os.getenv(
        "AUTH_MODE",
        AUTH_MODE_DEVELOPMENT,
    ).strip().lower()

    if mode not in {AUTH_MODE_DEVELOPMENT, AUTH_MODE_PRODUCTION}:
        raise ValueError(
            "Unsupported AUTH_MODE. Expected 'development' or 'production'."
        )
    return mode


def _principal_for_mode(mode: str) -> Principal:
    if mode == AUTH_MODE_PRODUCTION:
        raise RuntimeError(
            "Production authentication is not configured. "
            "Connect a real identity provider before using AUTH_MODE=production."
        )

    role = os.getenv(
        "DEV_USER_ROLE",
        ROLE_ADMIN,
    ).strip()

    if role not in VALID_ROLES:
        raise ValueError(
            f"Unsupported DEV_USER_ROLE: {role}. "
            f"Expected one of: {sorted(VALID_ROLES)}"
        )

    return Principal(
        subject=os.getenv(
            "DEV_USER_SUBJECT",
            "local-demo-user",
        ),
        display_name=os.getenv(
            "DEV_USER_NAME",
            "Local Demo User",
        ),
        email=os.getenv(
            "DEV_USER_EMAIL",
            "demo@local.invalid",
        ),
        role=role,
    )


def get_current_principal() -> Principal:
    """Development env roles are demo inputs; production deliberately fails closed."""
    return _principal_for_mode(get_auth_mode())


def get_startup_context() -> StartupContext:
    """Fail closed before importing side-effectful application dependencies.

    Resolve mode once so the identity decision and demo-seeding boundary use the
    same configuration snapshot. No production identity provider is implemented.
    """
    mode = get_auth_mode()
    return StartupContext(mode, _principal_for_mode(mode))
