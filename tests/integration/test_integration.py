"""Integration tests — require passwordless SSH to localhost.

These tests validate the SSH layer against a real SSH server.
They do NOT test `amplifier run` (which may not be installed).

All tests are auto-skipped by conftest.py if localhost SSH is unavailable.
"""

import time
import uuid

import pytest

from tool_remote_task.ssh import SSHClient


@pytest.mark.integration
def test_ssh_connect_and_run_command():
    """SSHClient can connect to localhost and run a simple command."""
    client = SSHClient()
    client.connect("localhost")

    stdout, stderr, exit_code = client.run_command("echo hello")
    client.close()

    assert exit_code == 0
    assert "hello" in stdout


@pytest.mark.integration
def test_ssh_run_command_captures_exit_code():
    """SSHClient captures non-zero exit codes."""
    client = SSHClient()
    client.connect("localhost")

    _, _, exit_code = client.run_command("exit 42")
    client.close()

    assert exit_code == 42


@pytest.mark.integration
def test_ssh_run_background_returns_valid_pid():
    """run_background returns a PID that is actually running."""
    client = SSHClient()
    client.connect("localhost")

    pid = client.run_background("sleep 5")
    assert pid > 0

    # Verify the PID is running
    _, _, exit_code = client.run_command(f"ps -p {pid}")
    assert exit_code == 0

    # Clean up
    client.run_command(f"kill {pid}")
    client.close()


@pytest.mark.integration
def test_ssh_background_writes_output_file():
    """A backgrounded command can write output to a temp file."""
    client = SSHClient()
    client.connect("localhost")

    file_id = str(uuid.uuid4())
    output_file = f"/tmp/amplifier-test-{file_id}.out"

    # Background a command that writes to a file
    pid = client.run_background(f"echo 'test output' > {output_file} 2>&1")
    assert pid > 0

    # Wait for the command to finish writing
    time.sleep(1)

    # Read the output file
    stdout, _, exit_code = client.run_command(f"cat {output_file}")
    assert exit_code == 0
    assert "test output" in stdout

    # Cleanup
    client.run_command(f"rm -f {output_file}")
    client.close()


@pytest.mark.integration
def test_ssh_connect_bad_host_raises():
    """Connecting to a non-existent host raises an exception."""
    client = SSHClient()
    with pytest.raises(Exception):
        client.connect("nonexistent.invalid.host.example.com", port=22)
    client.close()
