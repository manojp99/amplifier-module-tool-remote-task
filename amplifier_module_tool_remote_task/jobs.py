"""In-memory job store for tracking async remote tasks."""

import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass
class Job:
    """A single async remote task job."""

    job_id: str
    host: str
    remote_pid: int
    output_file: str
    ssh_port: int = 22
    ssh_key: str | None = None
    remote_session_id: str | None = None
    status: Literal["pending", "complete", "error"] = "pending"
    result: str | None = None


class JobStore:
    """In-memory store for async job handles.

    Jobs are lost if the local session dies. This is a v1 tradeoff.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create_job(
        self,
        host: str,
        remote_pid: int,
        output_file: str,
        ssh_port: int = 22,
        ssh_key: str | None = None,
        remote_session_id: str | None = None,
    ) -> str:
        """Create a new job and return its ID."""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(
            job_id=job_id,
            host=host,
            remote_pid=remote_pid,
            output_file=output_file,
            ssh_port=ssh_port,
            ssh_key=ssh_key,
            remote_session_id=remote_session_id,
        )
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """Look up a job by ID. Returns None if not found."""
        return self._jobs.get(job_id)

    def mark_complete(self, job_id: str, result: str) -> None:
        """Mark a job as complete with its result.

        Raises KeyError if job_id is not found.
        """
        job = self._jobs[job_id]
        job.status = "complete"
        job.result = result
