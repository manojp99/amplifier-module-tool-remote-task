"""Tool protocol classes for remote task dispatch and collection."""

import json
from typing import Any

from amplifier_core import ToolResult

from amplifier_module_tool_remote_task.jobs import JobStore
from amplifier_module_tool_remote_task.runner import RemoteTaskError, collect, run_async, run_sync
from amplifier_module_tool_remote_task.ssh import SSHClient


class RemoteTaskTool:
    """Delegate a task to a remote Amplifier agent session via SSH.

    Supports sync mode (wait for result) and async mode (return job_id).
    """

    def __init__(self, job_store: JobStore):
        self._job_store = job_store

    @property
    def name(self) -> str:
        return "remote_task"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to a remote Amplifier agent session via SSH. "
            "Use mode='sync' to wait for the result, or mode='async' to "
            "dispatch and collect later with remote_task_collect."
        )

    @property
    def input_schema(self) -> dict:
        return self.get_schema()

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": (
                        "SSH target, e.g. 'user@hostname' or 'hostname'"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "Task description to run on the remote agent",
                },
                "mode": {
                    "type": "string",
                    "enum": ["sync", "async"],
                    "description": (
                        "'sync' to wait for result, "
                        "'async' to return job_id immediately"
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds before giving up (sync mode only)",
                    "default": 300,
                },
                "ssh_port": {
                    "type": "integer",
                    "description": "SSH port on the remote host",
                    "default": 22,
                },
                "ssh_key": {
                    "type": "string",
                    "description": (
                        "Path to SSH private key "
                        "(falls back to SSH agent if omitted)"
                    ),
                },
                "working_dir": {
                    "type": "string",
                    "description": (
                        "Directory on the remote host to run Amplifier in. "
                        "Defaults to the SSH session home directory. "
                        "Use this to target a specific project, e.g. "
                        "'/home/user/myproject'."
                    ),
                },
            },
            "required": ["host", "task", "mode"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        host = input.get("host")
        task = input.get("task")
        mode = input.get("mode")

        if not host or not task or not mode:
            return ToolResult(
                success=False,
                error={
                    "message": "host, task, and mode are required",
                    "type": "ValidationError",
                },
            )

        if mode not in ("sync", "async"):
            return ToolResult(
                success=False,
                error={
                    "message": (
                        f"mode must be 'sync' or 'async', got '{mode}'"
                    ),
                    "type": "ValidationError",
                },
            )

        timeout = input.get("timeout", 300)
        ssh_port = input.get("ssh_port", 22)
        ssh_key = input.get("ssh_key")
        working_dir = input.get("working_dir")

        client = SSHClient()
        try:
            try:
                client.connect(host, port=ssh_port, key_path=ssh_key)
            except Exception as e:
                return ToolResult(
                    success=False,
                    error={
                        "message": (
                            f"SSH connection to {host} failed: {e}"
                        ),
                        "type": "SSHConnectionError",
                    },
                )

            if mode == "sync":
                result = run_sync(
                    client, task, host=host, timeout=timeout,
                    working_dir=working_dir,
                )
                return ToolResult(success=True, output=result)
            else:
                job_id = run_async(
                    client,
                    task,
                    host=host,
                    job_store=self._job_store,
                    ssh_port=ssh_port,
                    ssh_key=ssh_key,
                    working_dir=working_dir,
                )
                job = self._job_store.get_job(job_id)
                return ToolResult(
                    success=True,
                    output=json.dumps({
                        "status": "dispatched",
                        "job_id": job_id,
                        "remote_session_id": job.remote_session_id,
                    }),
                )
        except RemoteTaskError as e:
            return ToolResult(
                success=False,
                error={"message": str(e), "type": e.error_type},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"message": str(e), "type": "ExecutionError"},
            )
        finally:
            client.close()


class RemoteTaskCollectTool:
    """Collect the result of an async remote task by job ID."""

    def __init__(self, job_store: JobStore):
        self._job_store = job_store

    @property
    def name(self) -> str:
        return "remote_task_collect"

    @property
    def description(self) -> str:
        return (
            "Collect the result of an async remote task by job ID. "
            "Returns 'pending' if still running, or the result if complete."
        )

    @property
    def input_schema(self) -> dict:
        return self.get_schema()

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": (
                        "Job ID returned by a prior async remote_task call"
                    ),
                },
                "wait": {
                    "type": "boolean",
                    "description": (
                        "If true, block until job completes; "
                        "if false, return current status"
                    ),
                    "default": False,
                },
            },
            "required": ["job_id"],
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:
        job_id = input.get("job_id")

        if not job_id:
            return ToolResult(
                success=False,
                error={
                    "message": "job_id is required",
                    "type": "ValidationError",
                },
            )

        job = self._job_store.get_job(job_id)

        if job is None:
            return ToolResult(
                success=False,
                error={
                    "message": f"unknown job_id: {job_id}",
                    "type": "NotFoundError",
                },
            )

        # Fast path: already collected and cached
        if job.status == "complete":
            return ToolResult(success=True, output=job.result)

        wait = input.get("wait", False)

        client = SSHClient()
        try:
            try:
                client.connect(
                    job.host, port=job.ssh_port, key_path=job.ssh_key
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    error={
                        "message": (
                            f"SSH connection to {job.host} failed: {e}"
                        ),
                        "type": "SSHConnectionError",
                    },
                )

            result = collect(client, job, wait=wait)

            if result == "pending":
                return ToolResult(success=True, output="pending")

            self._job_store.mark_complete(job_id, result)
            return ToolResult(success=True, output=result)
        except RemoteTaskError as e:
            return ToolResult(
                success=False,
                error={"message": str(e), "type": e.error_type},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error={"message": str(e), "type": "ExecutionError"},
            )
        finally:
            client.close()
