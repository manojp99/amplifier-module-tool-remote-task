"""Tests for the sync/async task runner. All tests mock SSHClient."""
import pytest
from unittest.mock import MagicMock, patch

from tool_remote_task.jobs import Job, JobStore
from tool_remote_task.runner import (
    RemoteTaskError,
    collect,
    run_async,
    run_sync,
)


# --- Helpers ---


def _mock_client(run_command_return=None):
    """Create a MagicMock SSHClient with optional default run_command return."""
    client = MagicMock()
    if run_command_return is not None:
        client.run_command.return_value = run_command_return
    return client


# --- run_sync tests ---


def test_run_sync_returns_stdout_on_success():
    client = _mock_client(("task result\n", "", 0))
    result = run_sync(client, "describe the project", host="user@host")
    assert result == "task result"


def test_run_sync_uses_shlex_quote():
    client = _mock_client(("ok\n", "", 0))
    run_sync(client, "task with 'quotes' and spaces", host="user@host")
    command = client.run_command.call_args[0][0]
    # shlex.quote wraps in single quotes
    assert "amplifier run" in command
    assert "task with" in command


def test_run_sync_raises_not_installed_on_command_not_found():
    client = _mock_client(("", "bash: amplifier: command not found\n", 127))
    with pytest.raises(RemoteTaskError, match="amplifier is not installed on user@host"):
        run_sync(client, "do stuff", host="user@host")
    # Verify the error type
    try:
        run_sync(client, "do stuff", host="user@host")
    except RemoteTaskError as e:
        assert e.error_type == "NotInstalledError"


def test_run_sync_raises_task_failed_on_nonzero_exit():
    client = _mock_client(("", "something went wrong\n", 1))
    with pytest.raises(RemoteTaskError, match=r"remote task failed \(exit 1\)"):
        run_sync(client, "bad task", host="user@host")
    try:
        run_sync(client, "bad task", host="user@host")
    except RemoteTaskError as e:
        assert e.error_type == "TaskFailedError"


def test_run_sync_passes_timeout_to_client():
    client = _mock_client(("ok\n", "", 0))
    run_sync(client, "task", host="user@host", timeout=60)
    _, kwargs = client.run_command.call_args
    assert kwargs.get("timeout") == 60 or client.run_command.call_args[0][1] == 60


# --- run_async tests ---


def test_run_async_returns_job_id_string():
    client = MagicMock()
    client.run_background.return_value = 9876
    store = JobStore()

    job_id = run_async(client, "run tests", host="user@host", job_store=store)

    assert isinstance(job_id, str)
    assert len(job_id) > 0


def test_run_async_stores_job_with_correct_fields():
    client = MagicMock()
    client.run_background.return_value = 9876
    store = JobStore()

    job_id = run_async(client, "run tests", host="user@host", job_store=store)
    job = store.get_job(job_id)

    assert job is not None
    assert job.host == "user@host"
    assert job.remote_pid == 9876
    assert job.output_file.startswith("/tmp/amplifier-job-")
    assert job.output_file.endswith(".out")
    assert job.status == "pending"


def test_run_async_stores_ssh_connection_details():
    client = MagicMock()
    client.run_background.return_value = 9876
    store = JobStore()

    job_id = run_async(
        client,
        "run tests",
        host="user@host",
        job_store=store,
        ssh_port=2222,
        ssh_key="/path/to/key",
    )
    job = store.get_job(job_id)

    assert job.ssh_port == 2222
    assert job.ssh_key == "/path/to/key"


def test_run_async_command_redirects_to_output_file():
    client = MagicMock()
    client.run_background.return_value = 9876
    store = JobStore()

    run_async(client, "run tests", host="user@host", job_store=store)

    command = client.run_background.call_args[0][0]
    assert "amplifier run" in command
    assert "/tmp/amplifier-job-" in command
    assert "> " in command
    assert "2>&1" in command


# --- collect tests ---


def test_collect_returns_pending_when_process_running_and_no_wait():
    # ps -p returns exit code 0 → process is running
    client = _mock_client(("  PID TTY\n12345 ?\n", "", 0))
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    result = collect(client, job, wait=False)
    assert result == "pending"


def test_collect_returns_output_when_process_done():
    client = MagicMock()
    # Call 1: ps -p → not running (exit code 1)
    # Call 2: cat output file → success
    # Call 3: rm cleanup
    client.run_command.side_effect = [
        ("", "", 1),
        ("task output\n", "", 0),
        ("", "", 0),
    ]
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    result = collect(client, job, wait=False)
    assert result == "task output"


def test_collect_cleans_up_output_file():
    client = MagicMock()
    client.run_command.side_effect = [
        ("", "", 1),                  # ps -p → done
        ("task output\n", "", 0),     # cat → success
        ("", "", 0),                  # rm → cleanup
    ]
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    collect(client, job, wait=False)

    # Third call should be the rm -f cleanup
    rm_call = client.run_command.call_args_list[2]
    assert "rm -f /tmp/test.out" in rm_call[0][0]


@patch("tool_remote_task.runner.time.sleep")
def test_collect_wait_polls_until_done(mock_sleep):
    client = MagicMock()
    client.run_command.side_effect = [
        ("  PID\n12345\n", "", 0),    # initial ps -p → running
        ("", "", 1),                   # first poll → done
        ("task output\n", "", 0),      # cat → success
        ("", "", 0),                   # rm → cleanup
    ]
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    result = collect(client, job, wait=True, timeout=300)

    assert result == "task output"
    mock_sleep.assert_called_with(5)


@patch("tool_remote_task.runner.time.sleep")
def test_collect_wait_raises_on_timeout(mock_sleep):
    client = MagicMock()
    # Always running — never finishes
    client.run_command.return_value = ("  PID\n12345\n", "", 0)
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    with pytest.raises(RemoteTaskError, match="timeout waiting for job abc"):
        collect(client, job, wait=True, timeout=10)

    try:
        # Reset for second call
        client.run_command.return_value = ("  PID\n12345\n", "", 0)
        collect(client, job, wait=True, timeout=10)
    except RemoteTaskError as e:
        assert e.error_type == "TimeoutError"


def test_collect_raises_when_output_file_missing():
    client = MagicMock()
    client.run_command.side_effect = [
        ("", "", 1),                   # ps -p → done
        ("", "No such file\n", 1),     # cat → file not found
    ]
    job = Job(
        job_id="abc", host="user@host", remote_pid=12345,
        output_file="/tmp/test.out",
    )
    with pytest.raises(RemoteTaskError, match="output not found for job abc"):
        collect(client, job)
