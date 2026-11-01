r"""用密码 SSH 连阿里云那台机器，跑命令 / 传文件。

密码从环境变量 QQBOT_SSH_PASS 读，别放命令行参数里。

用法：
    $env:QQBOT_SSH_PASS = "你的root密码"
    .venv\Scripts\python.exe deploy\tencent\remote.py check
    .venv\Scripts\python.exe deploy\tencent\remote.py upload
    .venv\Scripts\python.exe deploy\tencent\remote.py install
    .venv\Scripts\python.exe deploy\tencent\remote.py cmd "free -m"
"""

from __future__ import annotations

import os
import sys
import time

import paramiko

# Windows 管道默认 cp1252，中文会炸
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HOST = os.environ.get("QQBOT_HOST", "")
USER = os.environ.get("QQBOT_USER", "root")
PORT = int(os.environ.get("QQBOT_PORT", "22"))

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARBALL = os.path.join(ROOT, "dist", "qqbot-deploy.tar.gz")


def connect() -> paramiko.SSHClient:
    pwd = os.environ.get("QQBOT_SSH_PASS")
    if not HOST:
        sys.exit("先设 QQBOT_HOST 环境变量（服务器 IP）")
    if not pwd:
        sys.exit("先设 QQBOT_SSH_PASS 环境变量")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(
        HOST, port=PORT, username=USER, password=pwd,
        timeout=20, banner_timeout=20, auth_timeout=20,
        look_for_keys=False, allow_agent=False,
    )
    return cli


def run(cli: paramiko.SSHClient, cmd: str, timeout: float = 1800.0) -> int:
    print(f"\n$ {cmd}", flush=True)
    chan = cli.get_transport().open_session()
    chan.settimeout(30)
    chan.exec_command(cmd)
    deadline = time.time() + timeout
    while True:
        if chan.recv_ready():
            sys.stdout.write(chan.recv(4096).decode("utf-8", "replace"))
            sys.stdout.flush()
        if chan.recv_stderr_ready():
            sys.stdout.write(chan.recv_stderr(4096).decode("utf-8", "replace"))
            sys.stdout.flush()
        if chan.exit_status_ready():
            while chan.recv_ready():
                sys.stdout.write(chan.recv(4096).decode("utf-8", "replace"))
            while chan.recv_stderr_ready():
                sys.stdout.write(chan.recv_stderr(4096).decode("utf-8", "replace"))
            sys.stdout.flush()
            code = chan.recv_exit_status()
            print(f"\n[exit {code}]", flush=True)
            return code
        if time.time() > deadline:
            chan.close()
            print("\n[超时]", flush=True)
            return 124
        time.sleep(0.2)


def upload(cli: paramiko.SSHClient) -> None:
    if not os.path.exists(TARBALL):
        sys.exit(f"找不到 {TARBALL}，先跑 pack.ps1")
    size = os.path.getsize(TARBALL) / 1024 / 1024
    print(f"上传 {TARBALL} ({size:.1f} MB) -> /root/qqbot-deploy.tar.gz", flush=True)
    sftp = cli.open_sftp()
    last = [0.0]

    def cb(done: int, total: int) -> None:
        if time.time() - last[0] > 2:
            last[0] = time.time()
            print(f"  {done / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB", flush=True)

    sftp.put(TARBALL, "/root/qqbot-deploy.tar.gz", callback=cb)
    sftp.close()
    print("上传完成", flush=True)


CHECK = [
    "cat /etc/os-release | head -3",
    "nproc; free -m | head -2",
    "df -h / | tail -1",
    "python3 -V",
]

INSTALL = [
    "mkdir -p /opt/qqbot",
    "tar -xzf /root/qqbot-deploy.tar.gz -C /opt/qqbot",
    "sed -i 's/^AI_IMAGE_OCR=.*/AI_IMAGE_OCR=false/' /opt/qqbot/.env",
    "bash /opt/qqbot/deploy/tencent/bootstrap.sh",
]


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    cli = connect()
    try:
        if action == "check":
            for c in CHECK:
                run(cli, c, timeout=120)
        elif action == "upload":
            upload(cli)
        elif action == "install":
            for c in INSTALL:
                code = run(cli, c)
                if code != 0:
                    sys.exit(f"步骤失败，退出码 {code}：{c}")
        elif action == "cmd":
            run(cli, sys.argv[2])
        elif action == "put":
            sftp = cli.open_sftp()
            sftp.put(sys.argv[2], sys.argv[3])
            sftp.close()
            print(f"已上传 {sys.argv[2]} -> {sys.argv[3]}", flush=True)
        elif action == "get":
            sftp = cli.open_sftp()
            sftp.get(sys.argv[2], sys.argv[3])
            sftp.close()
            print(f"已下载 {sys.argv[2]} -> {sys.argv[3]}", flush=True)
        else:
            sys.exit(f"不认识的命令：{action}")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
