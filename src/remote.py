import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

from config import File
from core import Instance, logger, relative_file


def run(cmd: str, *, check: bool = False) -> subprocess.CompletedProcess:
    try:
        ssh_cmd = ["ssh", "cryptonia.in", cmd]
        logger.debug(f"$ {shlex.join(ssh_cmd)}")
        p = subprocess.run(
            ssh_cmd,
            encoding="utf8",
            stdout=subprocess.PIPE,
            check=check,
        )
        if logger.isEnabledFor(logging.DEBUG):
            if p.stderr is not None and p.stderr != "":
                for line in p.stderr.splitlines():
                    logger.debug(f"stderr: {line}")
            if p.stdout is not None and p.stdout != "":
                for line in p.stdout.splitlines():
                    logger.debug(f"stdout: {line}")
        return p
    except subprocess.CalledProcessError as e:
        logger.error(f"when running: {cmd}")
        sys.exit(e.returncode)


def capture(cmd: str) -> str:
    return run(cmd, check=True).stdout


def resolve(remote_file: str) -> str:
    assert remote_file.startswith(("/", "~"))
    return capture(f'readlink --canonicalize "{remote_file}"').strip()


def fetch(ins: Instance, *, remote_file: str, local_file: Path) -> None:
    assert remote_file.startswith("/")
    if remote_file.startswith(ins.server.remote_path):
        short_remote_file = remote_file.removeprefix(ins.server.remote_path).lstrip("/")
    else:
        short_remote_file = Path(remote_file).name

    if remote_file in ins.mtimes:
        remote_mtime = ins.mtimes[remote_file]
        if local_file.exists():
            local_mtime = int(local_file.stat().st_mtime)
            if local_mtime == remote_mtime:
                print(f"{short_remote_file} up to date")
                return
    else:
        remote_mtime = int(capture(f"stat -c '%Y' {remote_file}").strip())

    print(f"\x1b[1;32mdownloading {short_remote_file}\x1b[0m")
    if remote_file.endswith("/"):
        local_file = local_file.parent
        remote_file = remote_file.rstrip("/")
    remote_file = resolve(remote_file)

    cmd = [
        "rsync",
        "--archive",
        "--delete",
        f"cryptonia.in:{remote_file}",
        str(local_file),
    ]
    logger.debug(f"$ {shlex.join(cmd)}")
    subprocess.run(cmd, check=True)
    os.utime(local_file, (remote_mtime, remote_mtime))


def mirror_jar(ins: Instance, *, remote_link: str, local_link: Path) -> None:
    if local_link.exists():
        assert local_link.is_symlink(), local_link
    resolved_file = resolve(remote_link)
    assert resolved_file, remote_link
    jar_file = ins.jars_path / Path(resolved_file).name
    if jar_file.exists():
        print(f"{jar_file.name} up to date")
    else:
        fetch(
            ins,
            remote_file=resolved_file,
            local_file=jar_file,
        )
    local_link.unlink(missing_ok=True)
    local_link.symlink_to(relative_file(local_link, jar_file))


def mirror(ins: Instance, files: list[File]) -> None:
    for file in files:
        file.local.parent.mkdir(parents=True, exist_ok=True)
        fetch(ins, remote_file=file.remote, local_file=file.local)
