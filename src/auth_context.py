import os

from src.authz import Principal, ROLE_ADMIN, VALID_ROLES


AUTH_MODE_DEVELOPMENT = "development"
AUTH_MODE_PRODUCTION = "production"


def get_current_principal() -> Principal:
    """
    Resolve the current application principal.

    Development mode uses environment variables so RBAC can be tested without
    pretending that the MVP has production authentication.

    Production mode intentionally fails closed until a real identity provider
    is configured.
    """
    mode = os.getenv(
        "AUTH_MODE",
        AUTH_MODE_DEVELOPMENT,
    ).strip().lower()

    if mode == AUTH_MODE_PRODUCTION:
        raise RuntimeError(
            "Production authentication is not configured. "
            "Connect a real identity provider before using AUTH_MODE=production."
        )

    if mode != AUTH_MODE_DEVELOPMENT:
        raise ValueError(
            "Unsupported AUTH_MODE. Expected 'development' or 'production'."
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
