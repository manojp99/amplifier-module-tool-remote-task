"""SSH client wrapper around paramiko."""

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
        """Run a command in the background via nohup.

        Returns:
            The PID of the backgrounded process on the remote host.
        """
        wrapped = f"nohup {command} & echo $!"
        _stdin, stdout, _stderr = self._client.exec_command(wrapped)
        pid_str = stdout.read().decode().strip()
        return int(pid_str)

    def close(self) -> None:
        """Close the SSH connection."""
        self._client.close()
