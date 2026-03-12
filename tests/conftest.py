"""Root conftest — auto-skips integration tests when SSH target is unavailable.

Environment variables:
    SSH_TEST_HOST: SSH host to connect to (default: localhost)
    SSH_TEST_PORT: SSH port to connect to (default: 22)
    SSH_TEST_USER: SSH user (default: current user or testuser if port != 22)

Examples:
    # Use Docker container on port 2222 as testuser
    SSH_TEST_HOST=localhost SSH_TEST_PORT=2222 SSH_TEST_USER=testuser uv run pytest tests/integration/ -v

    # Use localhost SSH (default)
    uv run pytest tests/integration/ -v
"""

import os
import subprocess

import pytest


def _ssh_config() -> tuple[str, int, str]:
    """Return (host, port, user) from env vars with sensible defaults."""
    host = os.environ.get("SSH_TEST_HOST", "localhost")
    port = int(os.environ.get("SSH_TEST_PORT", "22"))
    default_user = "testuser" if port != 22 else None
    user = os.environ.get("SSH_TEST_USER", default_user)
    return host, port, user


def can_ssh_target() -> bool:
    """Check if passwordless SSH to the configured target is available."""
    host, port, user = _ssh_config()
    target = f"{user}@{host}" if user else host
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=3",
                "-o", "StrictHostKeyChecking=no",
                "-p", str(port),
                target,
                "echo", "ok",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests when SSH target is unavailable."""
    if not can_ssh_target():
        host, port, user = _ssh_config()
        target = f"{user}@{host}:{port}" if user else f"{host}:{port}"
        skip_marker = pytest.mark.skip(
            reason=f"SSH target not available ({target}). "
                   f"Set SSH_TEST_HOST/SSH_TEST_PORT/SSH_TEST_USER or start Docker: "
                   f"cd tests/docker && docker compose up -d"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_marker)


@pytest.fixture
def ssh_target() -> dict:
    """Fixture providing SSH connection details for integration tests."""
    host, port, user = _ssh_config()
    return {"host": host, "port": port, "user": user}
