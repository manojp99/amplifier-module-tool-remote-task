FROM ubuntu:22.04

RUN apt-get update && apt-get install -y openssh-server \
    && mkdir /var/run/sshd

# Create test user
RUN useradd -m -s /bin/bash testuser

# Configure sshd: key-only auth
RUN sed -i "s/#PasswordAuthentication yes/PasswordAuthentication no/" /etc/ssh/sshd_config && \
    sed -i "s/#PubkeyAuthentication yes/PubkeyAuthentication yes/" /etc/ssh/sshd_config

# SSH authorized_keys bind-mounted from host at runtime
RUN mkdir -p /home/testuser/.ssh && \
    chmod 700 /home/testuser/.ssh && \
    chown testuser:testuser /home/testuser/.ssh

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D", "-e"]
