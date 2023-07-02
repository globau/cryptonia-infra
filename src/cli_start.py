import subprocess
import sys
from configparser import ConfigParser

from core import Error, Paths, main_wrapper


def start_instance(name: str, cfg: ConfigParser, paths: Paths) -> None:
    image_name = f"cryptonia.{name}"

    print(f"build {image_name}")
    p = subprocess.run(
        ["docker", "build"] + ["--tag", image_name] + ["--network", "host"] + ["."]
    )
    if p.returncode != 0:
        sys.exit(p.returncode)

    malloc = cfg.get("server", "xmx", fallback="512M")

    print(f"running {image_name}")
    subprocess.run(
        ["docker", "run"]
        + ["--name", image_name]
        + ["--rm"]
        + ["--tty", "--interactive"]
        + ["--network", "host"]
        + ["--env", "TZ=Australia/Perth"]
        + ["--mount", f"type=bind,source={paths.local_path},target=/minecraft"]
        + [image_name]
        + [
            "java",
            f"-Xmx{malloc}",
            f"-Xms{malloc}",
            "-jar",
            cfg.get("server", "jar"),
            "nogui",
        ]
    )
    if p.returncode != 0:
        sys.exit(p.returncode)


def main() -> None:
    try:
        with main_wrapper() as (name, cfg, paths):
            start_instance(name, cfg, paths)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)


main()
