import os
import sys
from pathlib import Path

from ruamel.yaml import YAML

import remote
from config import Instance
from core import Error, main_wrapper


def yaml_replace(ins: Instance, filename: Path, path: str, value: str) -> None:
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
            if real_key not in ref:
                raise Error(f"{filename}: bad path '{path}': missing key")
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
                print(
                    f"\x1b[1;33m{filename.relative_to(ins.root_path)}: {path} -> {value}\x1b[0m"
                )
            break
    else:
        raise Error(f"{filename.relative_to(ins.root_path)}: replaced failed: {path}")

    mtime = filename.stat().st_mtime
    yaml.dump(data, filename)
    os.utime(filename, (mtime, mtime))


def properties_replace(ins: Instance, filename: Path, path: str, value: str) -> None:
    lines = filename.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#"):
            continue
        line_name, line_value = line.split("=", maxsplit=1)
        if line_name == path:
            if line_value != value:
                print(
                    f"\x1b[1;33m{filename.relative_to(ins.root_path)}: {path} -> {value}\x1b[0m"
                )
                lines[i] = f"{path}={value}"
            break
    else:
        raise Error(f"{filename.relative_to(ins.root_path)}: replaced failed: {path}")

    content = "\n".join(lines)
    mtime = filename.stat().st_mtime
    filename.write_text(f"{content}\n")
    os.utime(filename, (mtime, mtime))


def conf_replace(ins: Instance, filename: Path, path: str, value: str) -> None:
    lines = filename.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#") or line.strip() == "":
            continue
        line_name, line_value = line.split(":", maxsplit=1)
        if line_name == path:
            if line_value.lstrip() != value:
                print(
                    f"\x1b[1;33m{filename.relative_to(ins.root_path)}: {path} -> {value}\x1b[0m"
                )
                if not (value.isdigit() or value in ("true", "false")):
                    value = f'"{value}"'
                lines[i] = f"{path}: {value}"
            break
    else:
        raise Error(f"{filename.relative_to(ins.root_path)}: replaced failed: {path}")

    content = "\n".join(lines)
    mtime = filename.stat().st_mtime
    filename.write_text(f"{content}\n")
    os.utime(filename, (mtime, mtime))


def build_remote_mtimes(ins: Instance) -> None:
    config_files = [f.remote for f in ins.server.files]
    for plugin in ins.plugins.values():
        config_files.extend(f.remote for f in plugin.files)
    assert not any(name.endswith("/") for name in config_files)

    files = " ".join(config_files)
    stats = remote.capture(
        f"for N in {files}; do [[ -e $N ]] && stat -c '%Y %n' $N; done; exit 0"
    )
    for line in stats.splitlines():
        mtime, remote_file = line.split(" ", maxsplit=1)
        assert remote_file.startswith(ins.server.remote_path), remote_file
        ins.mtimes[remote_file] = int(mtime)


def check_config(ins: Instance) -> None:
    local_jar_files = {f.name for f in ins.plugins_path.glob("*.jar")}
    unhandled_jars = local_jar_files.copy()

    for plugin in ins.plugins.values():
        for jar_file in plugin.jar_files:
            if jar_file.name in unhandled_jars:
                unhandled_jars.remove(jar_file.name)

    if unhandled_jars:
        print("failed to find config entries for the following jars:")
        for name in sorted(unhandled_jars):
            print(f"- {name}")
        print("create [plugin:<name>] or add to existing section's 'jars' option")
        sys.exit(1)


def update_server_jar(ins: Instance) -> None:
    remote.mirror_jar(
        ins,
        remote_link=ins.server.jar_file.remote,
        local_link=ins.server.jar_file.local,
    )
    remote.mirror(ins, ins.server.files)


def update_plugin_jars(ins: Instance) -> None:
    jars: list[Path] = []
    for remote_jar in remote.capture(
        f"ls {ins.server.remote_path}/plugins/*.jar"
    ).splitlines():
        remote_path = Path(remote_jar)
        plugin_name = remote_path.stem
        filename = remote_path.name

        if plugin_name in ins.plugins and ins.plugins[plugin_name].disabled:
            print(f"Plugin {plugin_name} is disabled")
            continue

        plugin_jar = ins.plugins_path / filename
        remote.mirror_jar(
            ins,
            remote_link=remote_jar,
            local_link=plugin_jar,
        )
        jars.append(plugin_jar)

    for local_jar in ins.plugins_path.glob("*.jar"):
        if local_jar not in jars:
            print(f"deleting {local_jar.relative_to(ins.root_path)}")
            local_jar.unlink()


def update_plugin_files(ins: Instance) -> None:
    for plugin in ins.plugins.values():
        remote.mirror(ins, plugin.files)


def post_process_symlinks(ins: Instance) -> None:
    for link in ins.links:
        if not link.filename.exists() or str(link.filename.readlink()) != link.target:
            print(f"{link.filename.relative_to(ins.root_path)} -> {link.target}")
            link.filename.unlink(missing_ok=True)
            link.filename.symlink_to(link.target)


def post_process_replace_values(ins: Instance) -> None:
    for replacement in ins.replacements:
        suffix = replacement.filename.suffix
        if suffix == ".template":
            suffix = Path(replacement.filename.name.removesuffix(".template")).suffix
        for path, value in replacement.mappings.items():
            if suffix == ".yml":
                yaml_replace(ins, replacement.filename, path, value)
            elif suffix == ".properties":
                properties_replace(ins, replacement.filename, path, value)
            elif suffix == ".conf":
                conf_replace(ins, replacement.filename, path, value)
            else:
                raise NotImplementedError()


def mirror_server(ins: Instance) -> None:
    print(f"updating {ins}\n")

    check_config(ins)

    build_remote_mtimes(ins)

    update_server_jar(ins)
    update_plugin_jars(ins)
    update_plugin_files(ins)

    post_process_symlinks(ins)
    post_process_replace_values(ins)


def main() -> None:
    try:
        with main_wrapper() as (ins):
            mirror_server(ins)
    except Error as e:
        print(e, file=sys.stderr)
        sys.exit(1)


main()
