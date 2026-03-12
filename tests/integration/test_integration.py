"""Integration tests — require SSH access to a configured target.

These tests validate the SSH layer against a real SSH server.
They do NOT test `amplifier run` (which may not be installed).

All tests are auto-skipped by conftest.py if SSH target is unavailable.

Quick start with Docker:
    cd tests/docker && docker compose up -d
    SSH_TEST_HOST=localhost SSH_TEST_PORT=2222 SSH_TEST_USER=testuser uv run pytest tests/integration/ -v
"""

import time
import uuid

import pytest

from tool_remote_task.ssh import SSHClient


def _client(ssh_target: dict) -> SSHClient:
    """Connect an SSHClient to the test target."""
    host = ssh_target["host"]
    port = ssh_target["port"]
    user = ssh_target["user"]
    target = f"{user}@{host}" if user else host
    client = SSHClient()
    client.connect(target, port=port)
    return client


@pytest.mark.integration
def test_ssh_connect_and_run_command(ssh_target):
    """SSHClient can connect and run a simple command."""
    client = _client(ssh_target)
    stdout, stderr, exit_code = client.run_command("echo hello")
    client.close()

    assert exit_code == 0
    assert "hello" in stdout


@pytest.mark.integration
def test_ssh_run_command_captures_exit_code(ssh_target):
    """SSHClient captures non-zero exit codes."""
    client = _client(ssh_target)
    _, _, exit_code = client.run_command("exit 42")
    client.close()

    assert exit_code == 42


@pytest.mark.integration
def test_ssh_run_background_returns_valid_pid(ssh_target):
    """run_background returns a PID that is actually running."""
    client = _client(ssh_target)
    pid = client.run_background("sleep 5")
    assert pid > 0

    _, _, exit_code = client.run_command(f"ps -p {pid}")
    assert exit_code == 0

    client.run_command(f"kill {pid}")
    client.close()


@pytest.mark.integration
def test_ssh_background_writes_output_file(ssh_target):
    """A backgrounded command can write output to a temp file."""
    client = _client(ssh_target)
    file_id = str(uuid.uuid4())
    output_file = f"/tmp/amplifier-test-{file_id}.out"

    pid = client.run_background(f"echo 'test output' > {output_file} 2>&1")
    assert pid > 0

    time.sleep(1)

    stdout, _, exit_code = client.run_command(f"cat {output_file}")
    assert exit_code == 0
    assert "test output" in stdout

    client.run_command(f"rm -f {output_file}")
    client.close()


@pytest.mark.integration
def test_ssh_connect_bad_host_raises(ssh_target):
    """Connecting to a non-existent host raises an exception."""
    client = SSHClient()
    with pytest.raises(Exception):
        client.connect("nonexistent.invalid.host.example.com", port=22)
    client.close()
