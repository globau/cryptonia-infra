import os
import sys
from configparser import ConfigParser, SectionProxy
from pathlib import Path

from ruamel.yaml import YAML

import remote
from core import Error, Paths, main_wrapper, relative_file


def yaml_replace(*, paths: Paths, filename: Path, path: str, value: str) -> None:
    yaml = YAML()
    data = yaml.load(filename)

    if value.isdigit():
        value = int(value)

    ref = data
    for key in path.split(".")[0:-1]:
        real_key = key
        if isinstance(ref, dict):
            for k in ref:
                if k.lower() == key.lower():
                    real_key = k
                    break
            ref = ref[real_key]
        elif isinstance(ref, list):
            try:
                ref = ref[int(key)]
            except ValueError:
                raise Error(f"{filename}: bad path '{path}': expected int")
            except IndexError:
                raise Error(f"{filename}: bad path '{path}': index out of range")
        else:
            raise NotImplementedError()
    name = path.split(".")[-1].lower()
    for k in ref:
        if k.lower() == name:
            if ref[k] != value:
                ref[k] = value
                print(f"{filename.relative_to(paths.local_path)}: {path} -> {value}")
            break
    else:
        raise Error(
            f"{filename.relative_to(paths.local_path)}: replaced failed: {path}"
        )

    mtime = filename.stat().st_mtime
    yaml.dump(data, filename)
    os.utime(filename, (mtime, mtime))


def properties_replace(*, paths: Paths, filename: Path, name: str, value: str) -> None:
    lines = filename.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#"):
            continue
        line_name, line_value = line.split("=", maxsplit=1)
        if line_name == name:
            if line_value != value:
                print(f"{filename.relative_to(paths.local_path)}: {name} -> {value}")
                lines[i] = f"{name}={value}"
            break
    else:
        raise Error(
            f"{filename.relative_to(paths.local_path)}: replaced failed: {name}"
        )

    content = "\n".join(lines)
    mtime = filename.stat().st_mtime
    filename.write_text(f"{content}\n")
    os.utime(filename, (mtime, mtime))


def conf_replace(*, paths: Paths, filename: Path, name: str, value: str) -> None:
    lines = filename.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#") or line.strip() == "":
            continue
        line_name, line_value = line.split(":", maxsplit=1)
        if line_name == name:
            if line_value.lstrip() != value:
                print(f"{filename.relative_to(paths.local_path)}: {name} -> {value}")
                if not (value.isdigit() or value in ("true", "false")):
                    value = f'"{value}"'
                lines[i] = f"{name}: {value}"
            break
    else:
        raise Error(
            f"{filename.relative_to(paths.local_path)}: replaced failed: {name}"
        )

    content = "\n".join(lines)
    mtime = filename.stat().st_mtime
    filename.write_text(f"{content}\n")
    os.utime(filename, (mtime, mtime))


def build_remote_mtimes(*, paths: Paths, cfg: ConfigParser) -> None:
    config_files = [
        f"{paths.remote_path}/{name}" for name in cfg["server"]["config"].split(" ")
    ]
    for section_name in [s for s in cfg.sections() if s.startswith("plugin:")]:
        plugin_name = section_name[len("plugin:") :]
        config_files.extend(
            [
                f"{paths.remote_path}/plugins/{plugin_name}/{name}"
                for name in cfg.get(section_name, "config", fallback="").split(" ")
                if name
            ]
        )

    assert not any(name.endswith("/") for name in config_files)

    files = " ".join(config_files)
    stats = remote.capture(
        f"for N in {files}; do [[ -e $N ]] && stat -c '%Y %n' $N; done; exit 0"
    )
    for line in stats.splitlines():
        mtime, remote_file = line.split(" ", maxsplit=1)
        assert remote_file.startswith(paths.remote_path), remote_file
        paths.mtimes[remote_file] = int(mtime)


def update_server_jar(*, paths: Paths, server_cfg: SectionProxy) -> None:
    server_jar = server_cfg.get("jar")
    config_files = [
        n for n in server_cfg.get("config", fallback="").split(" ") if n != ""
    ]
    remote.mirror_jar(
        paths=paths,
        remote_link=f"{paths.remote_path}/{server_jar}",
        local_link=paths.local_path / server_jar,
    )
    remote.mirror(
        paths=paths,
        remote_path=paths.remote_path,
        local_path=paths.local_path,
        filenames=config_files,
    )


def update_plugin_jars(*, paths: Paths) -> None:
    jars: list[Path] = []
    for remote_jar in remote.capture(
        f"ls {paths.remote_path}/plugins/*.jar"
    ).splitlines():
        filename = Path(remote_jar).name
        remote.mirror_jar(
            paths=paths,
            remote_link=remote_jar,
            local_link=paths.local_plugins_path / filename,
        )
        jars.append(paths.local_plugins_path / filename)

    for local_jar in paths.local_plugins_path.glob("*.jar"):
        if local_jar not in jars:
            print(f"deleting {local_jar.relative_to(paths.local_path)}")
            local_jar.unlink()


def update_plugin_configs(*, paths: Paths, cfg: ConfigParser) -> None:
    jar_files = {f.name for f in paths.local_plugins_path.glob("*.jar")}
    unhandled_jars = jar_files.copy()
    extra_sections = []

    for section_name in [s for s in cfg.sections() if s.startswith("plugin:")]:
        name = section_name.removeprefix("plugin:")

        jar_names = [f"{name}.jar"]
        if cfg.has_option(section_name, "jars"):
            jar_names.extend(
                [
                    j.strip()
                    for j in cfg.get(section_name, "jars", fallback="").split(" ")
                    if j
                ]
            )
        for jar_name in jar_names:
            if jar_name in unhandled_jars:
                unhandled_jars.remove(jar_name)
            if not any(
                (paths.local_plugins_path / jar_name).exists() for jar_name in jar_names
            ):
                extra_sections.append(section_name)

        remote_plugin_path = f"{paths.remote_path}/plugins/{name}"
        local_plugin_path = paths.local_plugins_path / name
        assert remote.resolve(remote_plugin_path), remote_plugin_path
        local_plugin_path.mkdir(parents=True, exist_ok=True)
        remote.mirror(
            paths=paths,
            remote_path=remote_plugin_path,
            local_path=local_plugin_path,
            filenames=[
                n
                for n in cfg.get(section_name, "config", fallback="").split(" ")
                if n != ""
            ],
        )

    if unhandled_jars:
        print("failed to find config entries for the following jars:")
        for name in sorted(unhandled_jars):
            print(f"- {name}")
        print("create [plugin:<name>] or add to existing section's 'jars' option")

    if extra_sections:
        print("failed to find jars for the following config entries:")
        for name in sorted(extra_sections):
            print(f"- {name}")

    if unhandled_jars or extra_sections:
        sys.exit(1)


def post_process_replace_values(*, paths: Paths, cfg: ConfigParser) -> None:
    for section_name in [s for s in cfg.sections() if s.startswith("replace:")]:
        filename = section_name.split(":")[1]
        for name in cfg.options(section_name):
            if filename.endswith(".yml"):
                yaml_replace(
                    paths=paths,
                    filename=paths.local_path / filename,
                    path=name,
                    value=cfg.get(section_name, name),
                )
            elif filename.endswith(".properties"):
                properties_replace(
                    paths=paths,
                    filename=paths.local_path / filename,
                    name=name,
                    value=cfg.get(section_name, name),
                )
            elif filename.endswith(".conf"):
                conf_replace(
                    paths=paths,
                    filename=paths.local_path / filename,
                    name=name,
                    value=cfg.get(section_name, name),
                )
            else:
                raise NotImplementedError(filename)


def post_process_symlinks(*, paths: Paths, cfg: ConfigParser) -> None:
    for section_name in [s for s in cfg.sections() if s.startswith("link:")]:
        filename = paths.local_path / section_name.split(":")[1]
        target = Path(cfg.get(section_name, "target")).resolve()
        if filename.resolve() != target:
            relative_target = relative_file(filename, target)
            print(f"{filename.relative_to(paths.local_path)} -> {relative_target}")
            filename.unlink(missing_ok=True)
            filename.symlink_to(relative_target)


def mirror_server(name: str, cfg: ConfigParser, paths: Paths) -> None:
    print(f"updating {name}\n")

    build_remote_mtimes(paths=paths, cfg=cfg)

    update_server_jar(paths=paths, server_cfg=cfg["server"])
    update_plugin_jars(paths=paths)
    update_plugin_configs(paths=paths, cfg=cfg)

    post_process_symlinks(paths=paths, cfg=cfg)
    post_process_replace_values(paths=paths, cfg=cfg)


def main() -> None:
    try:
        with main_wrapper() as (name, cfg, paths):
            mirror_server(name, cfg, paths)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)


main()
