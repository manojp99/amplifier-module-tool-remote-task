"""SSH client wrapper around paramiko."""

import shlex

import paramiko


class SSHClient:
    """Thin wrapper around paramiko.SSHClient for remote command execution."""

    def __init__(self):
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def connect(
        self, host: str, port: int = 22, key_path: str | None = None
    ) -> None:
        """Connect to a remote host.

        Args:
            host: SSH target — either "user@hostname" or just "hostname".
            port: SSH port (default 22).
            key_path: Path to private key file. Falls back to SSH agent if None.
        """
        if "@" in host:
            username, hostname = host.split("@", 1)
        else:
            username, hostname = None, host

        kwargs: dict = {"hostname": hostname, "port": port}
        if username:
            kwargs["username"] = username
        if key_path:
            kwargs["key_filename"] = key_path

        self._client.connect(**kwargs)

    def run_command(
        self, command: str, timeout: int = 300
    ) -> tuple[str, str, int]:
        """Run a command and wait for it to finish.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        _stdin, stdout, stderr = self._client.exec_command(
            command, timeout=timeout
        )
        exit_code = stdout.channel.recv_exit_status()
        return stdout.read().decode(), stderr.read().decode(), exit_code

    def run_background(self, command: str) -> int:
        """Run a command in the background, fully detached from the SSH channel.

        Uses setsid to create a new process session so the process survives
        after the SSH channel closes. Wraps in bash -c so any output
        redirections inside the command (e.g. > output_file) take effect
        within the subshell. The outer </dev/null >/dev/null 2>&1 prevents
        the SSH channel from hanging on open file descriptors.

        Returns:
            The PID of the backgrounded process on the remote host.
        """
        pid_var = "$!"
        wrapped = (
            f"setsid bash -c {shlex.quote(command)} "
            f"</dev/null >/dev/null 2>&1 & echo {pid_var}"
        )
        _stdin, stdout, _stderr = self._client.exec_command(wrapped)
        pid_str = stdout.read().decode().strip()
        return int(pid_str)

    def close(self) -> None:
        """Close the SSH connection."""
        self._client.close()
