import os
import subprocess
import sys

from core import Error, Instance, main_wrapper


def start_instance(ins: Instance) -> None:
    image_name = f"cryptonia.{ins.name}"

    print(f"build {image_name}")
    p = subprocess.run(
        ["docker", "build"] + ["--tag", image_name] + ["--network", "host"] + ["."]
    )
    if p.returncode != 0:
        sys.exit(p.returncode)

    if os.environ.get("DEBUG"):
        cmd = []
    else:
        cmd = [
            "java",
            f"-Xmx{ins.server.xmx}",
            f"-Xms{ins.server.xmx}",
            "-jar",
            ins.server.jar_file.name,
            "nogui",
        ]

    print(f"running {image_name}")
    subprocess.run(
        ["docker", "run"]
        + ["--name", image_name]
        + ["--rm"]
        + ["--tty", "--interactive"]
        + ["--network", "host"]
        + ["--env", "TZ=Australia/Perth"]
        + ["--mount", f"type=bind,source={ins.instances_path},target=/minecraft"]
        + ["--workdir", f"/minecraft/{ins.name}"]
        + [image_name]
        + cmd
    )
    if p.returncode != 0:
        sys.exit(p.returncode)


def main() -> None:
    try:
        with main_wrapper() as (ins):
            start_instance(ins)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)


main()
