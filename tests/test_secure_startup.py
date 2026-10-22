"""Synthetic startup security checks without importing a database or file store."""
import ast
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from src.auth_context import (
    AUTH_MODE_DEVELOPMENT, AUTH_MODE_PRODUCTION, StartupContext, get_auth_mode,
    get_startup_context,
)
from src.authz import Principal, ROLE_VIEWER


APP = Path(__file__).resolve().parents[1] / "app.py"
DEMO_PRINCIPAL = Principal("synthetic-reviewer", "Synthetic reviewer", "synthetic@local.invalid", ROLE_VIEWER)


@pytest.mark.parametrize("mode,exception,message", [
    ("production", "RuntimeError", "Production authentication is not configured"),
    ("  PRODUCTION  ", "RuntimeError", "Production authentication is not configured"),
    ("unknown", "ValueError", "Unsupported AUTH_MODE"),
    ("", "ValueError", "Unsupported AUTH_MODE"),
])
def test_actual_app_refuses_auth_before_side_effectful_imports(tmp_path, mode, exception, message):
    # Run the real entry point in a fresh process. None of its database, storage,
    # third-party UI or workflow dependencies may even be imported on refusal.
    script = """
import importlib.abc
import runpy
import sys

class BlockSideEffectImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        application = fullname.startswith('src.') and fullname not in {'src.auth_context', 'src.authz'}
        dependencies = fullname.split('.')[0] in {'pandas', 'plotly', 'streamlit', 'sqlalchemy', 'boto3'}
        if application or dependencies:
            raise AssertionError('Dependency imported before authentication refusal: ' + fullname)

sys.path.insert(0, sys.argv[1])
sys.meta_path.insert(0, BlockSideEffectImports())
try:
    runpy.run_path(sys.argv[2], run_name='__main__')
except (RuntimeError, ValueError) as error:
    assert type(error).__name__ == sys.argv[3]
    assert sys.argv[4] in str(error)
else:
    raise AssertionError('Unauthenticated startup was allowed')
"""
    env = dict(os.environ, AUTH_MODE=mode, DEV_USER_ROLE="Admin", STORAGE_BACKEND="s3")
    result = subprocess.run(
        [sys.executable, "-c", script, str(APP.parent), str(APP), exception, message],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.iterdir())


def startup_statements():
    """Execute the actual entry-point startup statements with inert dependencies.

    Imports are excluded, and execution ends before application page definitions;
    this makes development/future-provider ordering testable without live state.
    """
    nodes = []
    for node in ast.parse(APP.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PAGE_PERMISSIONS"
                                               for t in node.targets):
            break
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
    return compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec")


def run_startup(mode, *, healthy=True, auth_error=None):
    calls = []
    context = StartupContext(mode, DEMO_PRINCIPAL)
    session = object()
    storage = object()

    def authenticate():
        calls.append("authenticate")
        if auth_error:
            raise auth_error
        return context

    def stop():
        raise RuntimeError("synthetic UI stopped")

    def health(_):
        calls.append("health")
        return {"healthy": healthy, "message": "synthetic health", "missing_tables": []}

    def seed(actual_session):
        assert actual_session is session
        calls.append("seed")

    namespace = {
        "get_startup_context": authenticate,
        # Exercise the unchanged legacy initialization path after the new
        # side-effect-free navigation gate. Real demo startup is AppTest-covered.
        "select_app_page": lambda principal: calls.append("navigation") or "Control Tower",
        "st": SimpleNamespace(set_page_config=lambda **kwargs: calls.append("UI"),
                              error=lambda *args: None, write=lambda *args: None, stop=stop),
        "init_db": lambda: calls.append("init_db"),
        "check_database_health": health,
        "engine": object(),
        "get_session": lambda: calls.append("session") or session,
        "seed_demo_data": seed,
        "get_evidence_storage": lambda: calls.append("storage") or storage,
    }
    return calls, namespace


def test_development_startup_preserves_order_and_demo_behavior():
    calls, namespace = run_startup(AUTH_MODE_DEVELOPMENT)
    exec(startup_statements(), namespace)
    assert calls == ["authenticate", "UI", "navigation", "init_db", "health", "session", "seed", "storage"]
    assert namespace["CURRENT_USER"] is DEMO_PRINCIPAL


def test_future_authenticated_production_path_never_seeds_demo_data():
    # This is an injected hypothetical future provider result, not an enabled IdP.
    # The real production resolver still refuses startup in the subprocess test.
    calls, namespace = run_startup(AUTH_MODE_PRODUCTION)
    exec(startup_statements(), namespace)
    assert "seed" not in calls
    assert calls == ["authenticate", "UI", "navigation", "init_db", "health", "session", "storage"]


def test_authentication_failure_prevents_all_startup_callbacks():
    calls, namespace = run_startup(AUTH_MODE_PRODUCTION, auth_error=RuntimeError("synthetic auth refusal"))
    with pytest.raises(RuntimeError, match="synthetic auth refusal"):
        exec(startup_statements(), namespace)
    assert calls == ["authenticate"]


def test_unhealthy_database_stops_before_session_seed_or_storage():
    calls, namespace = run_startup(AUTH_MODE_DEVELOPMENT, healthy=False)
    with pytest.raises(RuntimeError, match="synthetic UI stopped"):
        exec(startup_statements(), namespace)
    assert calls == ["authenticate", "UI", "navigation", "init_db", "health"]


def test_development_mode_is_configuration_not_verified_identity(monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.setenv("DEV_USER_ROLE", ROLE_VIEWER)
    monkeypatch.setenv("DEV_USER_SUBJECT", "synthetic-demo-subject")
    context = get_startup_context()
    assert context.mode == AUTH_MODE_DEVELOPMENT and context.development_demo_seed_allowed
    assert context.principal.role == ROLE_VIEWER
    assert context.principal.subject == "synthetic-demo-subject"
    monkeypatch.setenv("AUTH_MODE", AUTH_MODE_PRODUCTION)
    assert get_auth_mode() == AUTH_MODE_PRODUCTION  # mode alone never authenticates
    with pytest.raises(RuntimeError, match="Production authentication is not configured"):
        get_startup_context()
