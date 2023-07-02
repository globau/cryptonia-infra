import argparse
import contextlib
import os
import sys
from collections.abc import Generator
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


class Error(Exception):
    pass


@dataclass
class Paths:
    remote_path: str
    local_path: Path
    local_jars_path: Path
    local_plugins_path: Path
    mtimes: dict[str, int]


def relative_file(origin_file: Path, target_file: Path) -> Path:
    def _relative(origin_path: Path, target_path: Path) -> Path:
        try:
            return target_path.relative_to(origin_path)
        except ValueError:
            return Path("..") / _relative(origin_path.parent, target_path)

    return _relative(origin_file.parent, target_file.parent) / target_file.name


@contextlib.contextmanager
def main_wrapper() -> Generator[[str, ConfigParser, Paths], None, None]:
    os.chdir(Path(__file__).parent.parent)

    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="ini filename")
    args = parser.parse_args()
    name = args.filename.removesuffix(".ini").removesuffix(".")
    ini_file = Path.cwd() / f"{name}.ini"

    try:
        if not ini_file.exists():
            raise Error(f"failed to find {ini_file.name}")

        cfg = ConfigParser()
        with ini_file.open() as f:
            cfg.read_file(f)

        server_cfg = cfg["server"]

        local_path = Path.cwd() / f"instances/{name}"
        paths = Paths(
            remote_path=f"/home/kidzone/opt/{server_cfg['remote_path']}",
            local_path=local_path,
            local_jars_path=local_path / "jars",
            local_plugins_path=local_path / "plugins",
            mtimes={},
        )
        paths.local_jars_path.mkdir(parents=True, exist_ok=True)
        paths.local_plugins_path.mkdir(parents=True, exist_ok=True)

        yield ini_file.stem, cfg, paths
    except KeyboardInterrupt:
        sys.exit(3)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)
