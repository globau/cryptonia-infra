import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

from core import Paths, logger, relative_file


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


def fetch(*, paths: Paths, remote_file: str, local_file: Path) -> None:
    assert remote_file.startswith("/")
    if remote_file.startswith(paths.remote_path):
        short_remote_file = remote_file.removeprefix(paths.remote_path).lstrip("/")
    else:
        short_remote_file = Path(remote_file).name

    if remote_file in paths.mtimes:
        mtime = paths.mtimes[remote_file]
        if local_file.exists() and local_file.stat().st_mtime == mtime:
            print(f"{short_remote_file} up to date")
            return
    else:
        mtime = int(capture(f"stat -c '%Y' {remote_file}").strip())

    print(f"downloading {short_remote_file}")
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
    os.utime(local_file, (mtime, mtime))


def mirror_jar(*, paths: Paths, remote_link: str, local_link: Path) -> None:
    if local_link.exists():
        assert local_link.is_symlink(), local_link
    resolved_file = resolve(remote_link)
    assert resolved_file, remote_link
    jar_file = paths.local_jars_path / Path(resolved_file).name
    if jar_file.exists():
        print(f"{jar_file.name} up to date")
    else:
        fetch(
            paths=paths,
            remote_file=resolved_file,
            local_file=jar_file,
        )
    local_link.unlink(missing_ok=True)
    local_link.symlink_to(relative_file(local_link, jar_file))


def mirror(
    *, paths: Paths, remote_path: str, local_path: Path, filenames: list[str]
) -> None:
    for remote_file in filenames:
        local_file = local_path / remote_file
        local_file.parent.mkdir(parents=True, exist_ok=True)
        abs_remote_file = f"{remote_path}/{remote_file}"
        if local_file.exists() and local_file.stat().st_mtime == paths.mtimes.get(
            abs_remote_file, -1
        ):
            print(f"{abs_remote_file[len(paths.remote_path) + 1:]} up to date")
            continue
        fetch(paths=paths, remote_file=abs_remote_file, local_file=local_file)
