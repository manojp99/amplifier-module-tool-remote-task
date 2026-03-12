"""Root conftest — auto-skips integration tests when localhost SSH is unavailable."""

import subprocess

import pytest


def can_ssh_localhost() -> bool:
    """Check if passwordless SSH to localhost is available."""
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=2",
                "-o", "StrictHostKeyChecking=no",
                "localhost",
                "echo", "ok",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked @pytest.mark.integration when SSH is unavailable."""
    if not can_ssh_localhost():
        skip_marker = pytest.mark.skip(
            reason="localhost SSH not available"
        )
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_marker)
