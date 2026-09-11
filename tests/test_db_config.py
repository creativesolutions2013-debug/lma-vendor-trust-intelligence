import os
import subprocess
import sys


def run_database_url_probe(env):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.db import DATABASE_URL; "
                "print(DATABASE_URL)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_database_url_defaults_to_sqlite_when_unset():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    assert run_database_url_probe(env) == (
        "sqlite:////tmp/vendor_trust.db"
    )


def test_database_url_honors_environment_override():
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        "sqlite:////tmp/vendor_trust_config_test.db"
    )

    assert run_database_url_probe(env) == (
        "sqlite:////tmp/vendor_trust_config_test.db"
    )