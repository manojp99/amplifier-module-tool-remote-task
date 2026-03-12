"""Amplifier tool module for delegating tasks to remote agents via SSH."""

from amplifier_module_tool_remote_task.jobs import JobStore
from amplifier_module_tool_remote_task.tool import RemoteTaskCollectTool, RemoteTaskTool


async def mount(coordinator, config: dict | None = None) -> None:
    """Mount remote_task and remote_task_collect tools.

    Both tools share a single in-memory JobStore so that async jobs
    dispatched by remote_task can be collected by remote_task_collect.

    Args:
        coordinator: Amplifier ModuleCoordinator instance.
        config: Module configuration (unused in v1).
    """
    job_store = JobStore()
    remote_task = RemoteTaskTool(job_store)
    remote_task_collect = RemoteTaskCollectTool(job_store)
    await coordinator.mount("tools", remote_task, name=remote_task.name)
    await coordinator.mount(
        "tools", remote_task_collect, name=remote_task_collect.name
    )
