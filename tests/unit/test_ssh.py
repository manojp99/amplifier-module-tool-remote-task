"""Tests for the SSH client wrapper. All tests mock paramiko."""
from unittest.mock import MagicMock, patch

from amplifier_module_tool_remote_task.ssh import SSHClient


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_connect_parses_user_at_host(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.connect("alice@remote.example.com")

    mock_inner.connect.assert_called_once_with(
        hostname="remote.example.com", port=22, username="alice"
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_connect_hostname_only_no_username(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.connect("remote.example.com")

    mock_inner.connect.assert_called_once_with(
        hostname="remote.example.com", port=22
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_connect_with_custom_port(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.connect("remote.example.com", port=2222)

    mock_inner.connect.assert_called_once_with(
        hostname="remote.example.com", port=2222
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_connect_with_key_path(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.connect("remote.example.com", key_path="/home/user/.ssh/id_rsa")

    mock_inner.connect.assert_called_once_with(
        hostname="remote.example.com",
        port=22,
        key_filename="/home/user/.ssh/id_rsa",
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_connect_all_options(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.connect("alice@remote.example.com", port=2222, key_path="/key")

    mock_inner.connect.assert_called_once_with(
        hostname="remote.example.com",
        port=2222,
        username="alice",
        key_filename="/key",
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_run_command_returns_stdout_stderr_exit_code(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"hello world"
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_inner.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient()
    stdout, stderr, exit_code = client.run_command("echo hello", timeout=30)

    assert stdout == "hello world"
    assert stderr == ""
    assert exit_code == 0
    mock_inner.exec_command.assert_called_once_with("echo hello", timeout=30)


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_run_command_captures_nonzero_exit(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b""
    mock_stdout.channel.recv_exit_status.return_value = 1
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b"command failed"
    mock_inner.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    client = SSHClient()
    stdout, stderr, exit_code = client.run_command("bad command")

    assert stdout == ""
    assert stderr == "command failed"
    assert exit_code == 1


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_run_background_returns_pid(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"12345\n"
    mock_inner.exec_command.return_value = (MagicMock(), mock_stdout, MagicMock())

    client = SSHClient()
    pid = client.run_background("sleep 100")

    assert pid == 12345
    mock_inner.exec_command.assert_called_once_with(
        "setsid bash -c 'sleep 100' </dev/null >/dev/null 2>&1 & echo $!"
    )


@patch("amplifier_module_tool_remote_task.ssh.paramiko")
def test_close_closes_paramiko_client(mock_paramiko):
    mock_inner = MagicMock()
    mock_paramiko.SSHClient.return_value = mock_inner
    mock_paramiko.AutoAddPolicy.return_value = "auto_add"

    client = SSHClient()
    client.close()

    mock_inner.close.assert_called_once()
