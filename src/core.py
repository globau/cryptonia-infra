import argparse
import contextlib
import logging
import os
import sys
from collections.abc import Generator
from pathlib import Path

from config import Instance

logger = logging.getLogger("cryptonia-infra")


class Error(Exception):
    pass


def relative_file(origin_file: Path, target_file: Path) -> Path:
    def _relative(origin_path: Path, target_path: Path) -> Path:
        try:
            return target_path.relative_to(origin_path)
        except ValueError:
            return Path("..") / _relative(origin_path.parent, target_path)

    return _relative(origin_file.parent, target_file.parent) / target_file.name


class _StreamHandler(logging.StreamHandler):
    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        exc_info = sys.exc_info()[0]
        if exc_info and exc_info.__name__ == BrokenPipeError.__name__:
            sys.exit(0)
        super().handleError(record)


@contextlib.contextmanager
def main_wrapper() -> Generator[[Instance], None, None]:
    os.chdir(Path(__file__).parent.parent)

    handler = _StreamHandler(sys.stdout)
    logger.addHandler(handler)
    if os.environ.get("DEBUG"):
        logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="ini filename")
    args = parser.parse_args()
    name = args.filename.removesuffix(".ini").removesuffix(".")
    ini_file = Path.cwd() / f"{name}.ini"

    try:
        yield Instance(ini_file)
    except KeyboardInterrupt:
        sys.exit(3)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)
