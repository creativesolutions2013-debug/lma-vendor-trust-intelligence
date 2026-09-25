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


def test_database_url_defaults_to_persistent_sqlite():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    database_url = run_database_url_probe(env)

    assert database_url.startswith("sqlite:////")
    assert database_url.endswith(
        "/data/vendor_trust.db"
    )


def test_default_database_is_not_ephemeral_tmp():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    database_url = run_database_url_probe(env)

    assert "/tmp/vendor_trust.db" not in database_url


def test_default_data_directory_is_created():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.db import DATA_DIR; "
                "print(DATA_DIR.exists())"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.strip() == "True"


def test_database_url_honors_environment_override():
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        "sqlite:////tmp/vendor_trust_config_test.db"
    )

    assert run_database_url_probe(env) == (
        "sqlite:////tmp/vendor_trust_config_test.db"
    )