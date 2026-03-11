"""Tests for the in-memory job store."""

import pytest

from tool_remote_task.jobs import JobStore


def test_create_job_returns_string_id():
    store = JobStore()
    job_id = store.create_job(
        host="user@host", remote_pid=1234, output_file="/tmp/test.out"
    )
    assert isinstance(job_id, str)
    assert len(job_id) > 0


def test_get_job_returns_created_job():
    store = JobStore()
    job_id = store.create_job(
        host="user@host", remote_pid=1234, output_file="/tmp/test.out"
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.host == "user@host"
    assert job.remote_pid == 1234
    assert job.output_file == "/tmp/test.out"
    assert job.status == "pending"
    assert job.result is None


def test_get_job_not_found_returns_none():
    store = JobStore()
    assert store.get_job("nonexistent-id") is None


def test_create_job_stores_ssh_connection_details():
    store = JobStore()
    job_id = store.create_job(
        host="user@host",
        remote_pid=1234,
        output_file="/tmp/test.out",
        ssh_port=2222,
        ssh_key="/home/user/.ssh/id_ed25519",
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.ssh_port == 2222
    assert job.ssh_key == "/home/user/.ssh/id_ed25519"


def test_create_job_defaults_ssh_port_22():
    store = JobStore()
    job_id = store.create_job(
        host="user@host", remote_pid=1234, output_file="/tmp/test.out"
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.ssh_port == 22
    assert job.ssh_key is None


def test_mark_complete_updates_status_and_result():
    store = JobStore()
    job_id = store.create_job(
        host="user@host", remote_pid=1234, output_file="/tmp/test.out"
    )
    store.mark_complete(job_id, "task output here")
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "complete"
    assert job.result == "task output here"


def test_mark_complete_unknown_job_raises_key_error():
    store = JobStore()
    with pytest.raises(KeyError):
        store.mark_complete("nonexistent-id", "result")
