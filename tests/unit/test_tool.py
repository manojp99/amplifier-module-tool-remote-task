"""Tests for RemoteTaskTool and RemoteTaskCollectTool.

Mocks SSHClient and runner functions — no real SSH connections.
"""

import pytest
from unittest.mock import MagicMock, patch

from amplifier_module_tool_remote_task.jobs import JobStore
from amplifier_module_tool_remote_task.runner import RemoteTaskError
from amplifier_module_tool_remote_task.tool import RemoteTaskCollectTool, RemoteTaskTool


# ============================================================
# RemoteTaskTool
# ============================================================


class TestRemoteTaskToolProperties:
    def test_name_is_remote_task(self):
        tool = RemoteTaskTool(JobStore())
        assert tool.name == "remote_task"

    def test_description_is_nonempty_string(self):
        tool = RemoteTaskTool(JobStore())
        assert isinstance(tool.description, str)
        assert len(tool.description) > 10

    def test_schema_has_required_fields(self):
        tool = RemoteTaskTool(JobStore())
        schema = tool.get_schema()
        assert schema["required"] == ["host", "task", "mode"]
        props = schema["properties"]
        assert "host" in props
        assert "task" in props
        assert "mode" in props
        assert "timeout" in props
        assert "ssh_port" in props
        assert "ssh_key" in props

    def test_schema_mode_has_enum(self):
        tool = RemoteTaskTool(JobStore())
        schema = tool.get_schema()
        assert schema["properties"]["mode"]["enum"] == ["sync", "async"]


class TestRemoteTaskToolValidation:
    async def test_missing_host_returns_error(self):
        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({"task": "stuff", "mode": "sync"})
        assert not result.success
        assert "required" in result.error["message"]
        assert result.error["type"] == "ValidationError"

    async def test_missing_task_returns_error(self):
        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({"host": "user@host", "mode": "sync"})
        assert not result.success
        assert "required" in result.error["message"]

    async def test_missing_mode_returns_error(self):
        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({"host": "user@host", "task": "stuff"})
        assert not result.success
        assert "required" in result.error["message"]

    async def test_invalid_mode_returns_error(self):
        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({
            "host": "user@host", "task": "stuff", "mode": "invalid",
        })
        assert not result.success
        assert "sync" in result.error["message"]
        assert "async" in result.error["message"]
        assert result.error["type"] == "ValidationError"


class TestRemoteTaskToolSync:
    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_sync_success_returns_output(self, mock_run_sync, mock_ssh_class):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_run_sync.return_value = "task result"

        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({
            "host": "user@host", "task": "describe files", "mode": "sync",
        })

        assert result.success is True
        assert result.output == "task result"
        mock_client.connect.assert_called_once_with(
            "user@host", port=22, key_path=None
        )
        mock_run_sync.assert_called_once_with(
            mock_client, "describe files", host="user@host", timeout=300,
            working_dir=None,
        )
        mock_client.close.assert_called_once()

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_sync_custom_timeout(self, mock_run_sync, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_sync.return_value = "ok"

        tool = RemoteTaskTool(JobStore())
        await tool.execute({
            "host": "user@host", "task": "task", "mode": "sync", "timeout": 60,
        })

        assert mock_run_sync.call_args[1]["timeout"] == 60

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_sync_custom_ssh_port_and_key(self, mock_run_sync, mock_ssh_class):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_run_sync.return_value = "ok"

        tool = RemoteTaskTool(JobStore())
        await tool.execute({
            "host": "user@host", "task": "task", "mode": "sync",
            "ssh_port": 2222, "ssh_key": "/path/key",
        })

        mock_client.connect.assert_called_once_with(
            "user@host", port=2222, key_path="/path/key"
        )


class TestRemoteTaskToolAsync:
    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_async")
    async def test_async_returns_job_id(self, mock_run_async, mock_ssh_class):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_run_async.return_value = "job-abc-123"

        job_store = JobStore()
        # Pre-populate store so tool.execute can retrieve the job after run_async returns
        job_store.create_job.__func__  # ensure method exists
        from amplifier_module_tool_remote_task.jobs import Job
        job_store._jobs["job-abc-123"] = Job(
            job_id="job-abc-123", host="user@host", remote_pid=1234,
            output_file="/tmp/test.out", remote_session_id=None,
        )
        tool = RemoteTaskTool(job_store)
        result = await tool.execute({
            "host": "user@host", "task": "run tests", "mode": "async",
        })

        assert result.success is True
        assert "job-abc-123" in result.output
        mock_run_async.assert_called_once_with(
            mock_client, "run tests",
            host="user@host", job_store=job_store,
            ssh_port=22, ssh_key=None, working_dir=None,
        )
        mock_client.close.assert_called_once()

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_async")
    async def test_async_passes_ssh_details(self, mock_run_async, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_async.return_value = "job-123"

        job_store = JobStore()
        tool = RemoteTaskTool(job_store)
        await tool.execute({
            "host": "user@host", "task": "task", "mode": "async",
            "ssh_port": 2222, "ssh_key": "/key",
        })

        assert mock_run_async.call_args[1]["ssh_port"] == 2222
        assert mock_run_async.call_args[1]["ssh_key"] == "/key"


class TestRemoteTaskToolErrors:
    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    async def test_ssh_connection_failure(self, mock_ssh_class):
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("Connection refused")
        mock_ssh_class.return_value = mock_client

        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({
            "host": "user@host", "task": "stuff", "mode": "sync",
        })

        assert not result.success
        assert "SSH connection to user@host failed" in result.error["message"]
        assert "Connection refused" in result.error["message"]
        assert result.error["type"] == "SSHConnectionError"
        # Client close is still called (cleanup in finally)
        mock_client.close.assert_called_once()

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_amplifier_not_installed(self, mock_run_sync, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_sync.side_effect = RemoteTaskError(
            "amplifier is not installed on user@host", "NotInstalledError"
        )

        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({
            "host": "user@host", "task": "stuff", "mode": "sync",
        })

        assert not result.success
        assert "not installed" in result.error["message"]
        assert result.error["type"] == "NotInstalledError"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_task_failed_nonzero_exit(self, mock_run_sync, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_sync.side_effect = RemoteTaskError(
            "remote task failed (exit 1): error output", "TaskFailedError"
        )

        tool = RemoteTaskTool(JobStore())
        result = await tool.execute({
            "host": "user@host", "task": "bad task", "mode": "sync",
        })

        assert not result.success
        assert "remote task failed" in result.error["message"]
        assert result.error["type"] == "TaskFailedError"


# ============================================================
# RemoteTaskCollectTool
# ============================================================


class TestRemoteTaskCollectToolProperties:
    def test_name_is_remote_task_collect(self):
        tool = RemoteTaskCollectTool(JobStore())
        assert tool.name == "remote_task_collect"

    def test_description_is_nonempty_string(self):
        tool = RemoteTaskCollectTool(JobStore())
        assert isinstance(tool.description, str)
        assert len(tool.description) > 10

    def test_schema_has_required_fields(self):
        tool = RemoteTaskCollectTool(JobStore())
        schema = tool.get_schema()
        assert schema["required"] == ["job_id"]
        assert "job_id" in schema["properties"]
        assert "wait" in schema["properties"]


class TestRemoteTaskCollectToolValidation:
    async def test_missing_job_id_returns_error(self):
        tool = RemoteTaskCollectTool(JobStore())
        result = await tool.execute({})
        assert not result.success
        assert "job_id is required" in result.error["message"]
        assert result.error["type"] == "ValidationError"

    async def test_unknown_job_id_returns_error(self):
        tool = RemoteTaskCollectTool(JobStore())
        result = await tool.execute({"job_id": "nonexistent"})
        assert not result.success
        assert "unknown job_id: nonexistent" in result.error["message"]
        assert result.error["type"] == "NotFoundError"


class TestRemoteTaskCollectToolExecution:
    async def test_already_complete_returns_cached_result(self):
        store = JobStore()
        job_id = store.create_job(
            host="user@host", remote_pid=1234, output_file="/tmp/test.out"
        )
        store.mark_complete(job_id, "cached result")

        tool = RemoteTaskCollectTool(store)
        result = await tool.execute({"job_id": job_id})

        assert result.success is True
        assert result.output == "cached result"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.collect")
    async def test_pending_returns_pending(self, mock_collect, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_collect.return_value = "pending"

        store = JobStore()
        job_id = store.create_job(
            host="user@host", remote_pid=1234, output_file="/tmp/test.out"
        )

        tool = RemoteTaskCollectTool(store)
        result = await tool.execute({"job_id": job_id})

        assert result.success is True
        assert result.output == "pending"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.collect")
    async def test_complete_returns_result_and_marks_job(
        self, mock_collect, mock_ssh_class
    ):
        mock_ssh_class.return_value = MagicMock()
        mock_collect.return_value = "task output"

        store = JobStore()
        job_id = store.create_job(
            host="user@host", remote_pid=1234, output_file="/tmp/test.out"
        )

        tool = RemoteTaskCollectTool(store)
        result = await tool.execute({"job_id": job_id})

        assert result.success is True
        assert result.output == "task output"
        # Verify job was marked complete in the store
        job = store.get_job(job_id)
        assert job.status == "complete"
        assert job.result == "task output"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.collect")
    async def test_connects_using_stored_ssh_details(
        self, mock_collect, mock_ssh_class
    ):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client
        mock_collect.return_value = "ok"

        store = JobStore()
        job_id = store.create_job(
            host="alice@remote",
            remote_pid=1234,
            output_file="/tmp/test.out",
            ssh_port=2222,
            ssh_key="/path/to/key",
        )

        tool = RemoteTaskCollectTool(store)
        await tool.execute({"job_id": job_id})

        mock_client.connect.assert_called_once_with(
            "alice@remote", port=2222, key_path="/path/to/key"
        )
        mock_client.close.assert_called_once()

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    async def test_ssh_failure_during_collect(self, mock_ssh_class):
        mock_client = MagicMock()
        mock_client.connect.side_effect = Exception("Connection refused")
        mock_ssh_class.return_value = mock_client

        store = JobStore()
        job_id = store.create_job(
            host="user@host", remote_pid=1234, output_file="/tmp/test.out"
        )

        tool = RemoteTaskCollectTool(store)
        result = await tool.execute({"job_id": job_id})

        assert not result.success
        assert "SSH connection to user@host failed" in result.error["message"]
        mock_client.close.assert_called_once()

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.collect")
    async def test_timeout_during_collect(self, mock_collect, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_collect.side_effect = RemoteTaskError(
            "timeout waiting for job abc", "TimeoutError"
        )

        store = JobStore()
        job_id = store.create_job(
            host="user@host", remote_pid=1234, output_file="/tmp/test.out"
        )

        tool = RemoteTaskCollectTool(store)
        result = await tool.execute({"job_id": job_id})

        assert not result.success
        assert "timeout" in result.error["message"]
        assert result.error["type"] == "TimeoutError"


# ============================================================
# mount() entry point
# ============================================================


class TestMount:
    async def test_mount_registers_both_tools(self):
        from unittest.mock import AsyncMock

        from amplifier_module_tool_remote_task import mount

        coordinator = MagicMock()
        coordinator.mount = AsyncMock()

        await mount(coordinator, {})

        assert coordinator.mount.call_count == 2

        # Verify first call registers remote_task
        call_1 = coordinator.mount.call_args_list[0]
        assert call_1[0][0] == "tools"
        assert call_1[1]["name"] == "remote_task"

        # Verify second call registers remote_task_collect
        call_2 = coordinator.mount.call_args_list[1]
        assert call_2[0][0] == "tools"
        assert call_2[1]["name"] == "remote_task_collect"

    async def test_mount_tools_share_same_job_store(self):
        from unittest.mock import AsyncMock

        from amplifier_module_tool_remote_task import mount

        coordinator = MagicMock()
        coordinator.mount = AsyncMock()

        await mount(coordinator, {})

        # Both tools should share the same JobStore instance
        tool_1 = coordinator.mount.call_args_list[0][0][1]
        tool_2 = coordinator.mount.call_args_list[1][0][1]
        assert tool_1._job_store is tool_2._job_store

    async def test_mount_works_with_no_config(self):
        from unittest.mock import AsyncMock

        from amplifier_module_tool_remote_task import mount

        coordinator = MagicMock()
        coordinator.mount = AsyncMock()

        # Config defaults to None
        await mount(coordinator)

        assert coordinator.mount.call_count == 2


# ============================================================
# working_dir support
# ============================================================


class TestRemoteTaskToolWorkingDir:
    def test_schema_has_working_dir_property(self):
        tool = RemoteTaskTool(JobStore())
        schema = tool.get_schema()
        assert "working_dir" in schema["properties"]
        assert schema["properties"]["working_dir"]["type"] == "string"
        # Not required — optional
        assert "working_dir" not in schema["required"]

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_working_dir_passed_to_run_sync(self, mock_run_sync, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_sync.return_value = "ok"

        tool = RemoteTaskTool(JobStore())
        await tool.execute({
            "host": "user@host", "task": "list files", "mode": "sync",
            "working_dir": "/projects/myapp",
        })

        assert mock_run_sync.call_args[1]["working_dir"] == "/projects/myapp"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_async")
    async def test_working_dir_passed_to_run_async(self, mock_run_async, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_async.return_value = "job-123"

        tool = RemoteTaskTool(JobStore())
        await tool.execute({
            "host": "user@host", "task": "run tests", "mode": "async",
            "working_dir": "/projects/myapp",
        })

        assert mock_run_async.call_args[1]["working_dir"] == "/projects/myapp"

    @patch("amplifier_module_tool_remote_task.tool.SSHClient")
    @patch("amplifier_module_tool_remote_task.tool.run_sync")
    async def test_working_dir_defaults_to_none(self, mock_run_sync, mock_ssh_class):
        mock_ssh_class.return_value = MagicMock()
        mock_run_sync.return_value = "ok"

        tool = RemoteTaskTool(JobStore())
        await tool.execute({
            "host": "user@host", "task": "task", "mode": "sync",
        })

        assert mock_run_sync.call_args[1]["working_dir"] is None
