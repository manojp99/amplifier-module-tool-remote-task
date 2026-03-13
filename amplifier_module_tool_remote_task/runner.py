"""Sync and async task runner — orchestrates SSH commands for remote Amplifier sessions."""

import shlex
import time
import uuid

from amplifier_module_tool_remote_task.jobs import Job, JobStore
from amplifier_module_tool_remote_task.ssh import SSHClient


class RemoteTaskError(Exception):
    """Error during remote task execution.

    Attributes:
        error_type: Machine-readable error category for ToolResult.
    """

    def __init__(self, message: str, error_type: str):
        super().__init__(message)
        self.error_type = error_type



def _poll_session_id(
    client: SSHClient,
    output_file: str,
    timeout: int = 10,
) -> str | None:
    """Poll the output file for the Amplifier session ID.

    Amplifier prints 'Session ID: <uuid>' in the first few lines of
    output. We poll the temp file for up to `timeout` seconds to
    extract it before returning to the caller.

    Returns the session ID string, or None if not found in time.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        stdout, _, exit_code = client.run_command(
            f"grep -m1 'Session ID:' {output_file} 2>/dev/null",
            timeout=5,
        )
        if exit_code == 0 and stdout.strip():
            parts = stdout.strip().split("Session ID:")
            if len(parts) == 2:
                return parts[1].strip()
    return None


def run_sync(
    client: SSHClient,
    task: str,
    host: str,
    timeout: int = 300,
    working_dir: str | None = None,
) -> str:
    """Run a task synchronously on a remote host and return the output.

    Args:
        client: Connected SSH client.
        task: Natural language task description.
        host: SSH target (for error messages).
        timeout: Max seconds to wait (default 300).
        working_dir: Remote directory to run Amplifier in. If None, uses
            the SSH session default (typically the home directory).

    Raises:
        RemoteTaskError: If amplifier is not installed or the task fails.
    """
    amplifier_cmd = f"amplifier run {shlex.quote(task)}"
    if working_dir:
        command = f"cd {shlex.quote(working_dir)} && {amplifier_cmd}"
    else:
        command = amplifier_cmd
    stdout, stderr, exit_code = client.run_command(command, timeout=timeout)

    if exit_code != 0:
        if "command not found" in stderr:
            raise RemoteTaskError(
                f"amplifier is not installed on {host}",
                "NotInstalledError",
            )
        raise RemoteTaskError(
            f"remote task failed (exit {exit_code}): {stderr or stdout}",
            "TaskFailedError",
        )

    return stdout.strip()


def run_async(
    client: SSHClient,
    task: str,
    host: str,
    job_store: JobStore,
    ssh_port: int = 22,
    ssh_key: str | None = None,
    working_dir: str | None = None,
) -> str:
    """Dispatch a task asynchronously on a remote host and return a job ID.

    The command runs in the background. Output is redirected to a temp
    file on the remote host. The job is tracked in the local job store
    for later collection.

    Args:
        working_dir: Remote directory to run Amplifier in. If None, uses
            the SSH session default (typically the home directory).
    """
    file_id = str(uuid.uuid4())
    output_file = f"/tmp/amplifier-job-{file_id}.out"
    amplifier_cmd = f"amplifier run {shlex.quote(task)} > {output_file} 2>&1"
    if working_dir:
        command = f"cd {shlex.quote(working_dir)} && {amplifier_cmd}"
    else:
        command = amplifier_cmd
    pid = client.run_background(command)

    remote_session_id = _poll_session_id(client, output_file)

    job_id = job_store.create_job(
        host=host,
        remote_pid=pid,
        output_file=output_file,
        ssh_port=ssh_port,
        ssh_key=ssh_key,
        remote_session_id=remote_session_id,
    )
    return job_id


def collect(
    client: SSHClient,
    job: Job,
    wait: bool = False,
    timeout: int = 300,
) -> str:
    """Collect the result of an async remote task.

    Args:
        client: Connected SSH client to the job's host.
        job: The job to collect.
        wait: If True, poll until the process finishes (up to timeout).
        timeout: Max seconds to wait when wait=True.

    Returns:
        "pending" if the process is still running and wait=False.
        The task output string if the process is done.

    Raises:
        RemoteTaskError: On timeout or missing output file.
    """
    _, _, exit_code = client.run_command(
        f"ps -p {job.remote_pid}", timeout=10
    )
    is_running = exit_code == 0

    if is_running and not wait:
        return "pending"

    if is_running and wait:
        elapsed = 0
        while elapsed < timeout:
            time.sleep(5)
            elapsed += 5
            _, _, exit_code = client.run_command(
                f"ps -p {job.remote_pid}", timeout=10
            )
            if exit_code != 0:
                break
        else:
            raise RemoteTaskError(
                f"timeout waiting for job {job.job_id}",
                "TimeoutError",
            )

    # Process is done — read output file
    stdout, _, exit_code = client.run_command(
        f"cat {job.output_file}", timeout=30
    )
    if exit_code != 0:
        # Fallback: if the temp file is gone but we have the remote
        # session ID, use `amplifier session show` to retrieve output.
        if job.remote_session_id:
            fallback_stdout, _, fallback_exit = client.run_command(
                f"amplifier session show {job.remote_session_id}",
                timeout=30,
            )
            if fallback_exit == 0 and fallback_stdout.strip():
                client.run_command(f"rm -f {job.output_file}", timeout=10)
                return fallback_stdout.strip()
        raise RemoteTaskError(
            f"output not found for job {job.job_id}",
            "OutputNotFoundError",
        )

    # Cleanup temp file on remote
    client.run_command(f"rm -f {job.output_file}", timeout=10)

    return stdout.strip()
