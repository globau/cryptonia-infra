import re
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class File:
    name: str
    local: Path
    remote: str

    def __init__(self, name: str, local_path: Path, remote_path: str) -> None:
        assert remote_path.startswith("/"), remote_path
        self.name = name
        self.local = local_path / name
        self.remote = f"{remote_path}/{name}"


@dataclass
class Link:
    filename: Path
    target: str

    def __init__(
        self, cfg: ConfigParser, section_name: str, instance_path: Path
    ) -> None:
        assert section_name.startswith("link:")
        name = section_name.removeprefix("link:")
        self.filename = instance_path / name
        self.target = cfg.get(section_name, "target")


@dataclass
class Replace:
    filename: Path
    mappings: dict[str, str]

    def __init__(
        self, cfg: ConfigParser, section_name: str, instance_path: Path
    ) -> None:
        assert section_name.startswith("replace:")
        self.filename = instance_path / section_name.removeprefix("replace:")
        self.mappings = {}
        for path in cfg.options(section_name):
            self.mappings[path] = cfg.get(section_name, path)


@dataclass
class _Common:
    _remote_path: str
    files: list[File]

    def __init__(
        self,
        cfg: ConfigParser,
        section_name: str,
        local_path: Path,
        remote_path: str,
    ) -> None:
        section = cfg[section_name]
        self.files = [
            File(name=f, local_path=local_path, remote_path=remote_path)
            for f in re.split(r"\s+", section.get("files", fallback=""))
            if f
        ]


@dataclass
class Server(_Common):
    remote_path: str
    jar_file: File
    xmx: str

    def __init__(self, cfg: ConfigParser, local_path: Path, opt_path: str) -> None:
        self.remote_path = f"{opt_path}/{cfg.get('server', 'remote_path')}"
        super().__init__(cfg, "server", local_path, self.remote_path)
        self.xmx = cfg.get("server", "xmx", fallback="512M")
        self.jar_file = File(
            cfg["server"].get("jar", fallback="server.jar"),
            local_path,
            self.remote_path,
        )

    def __repr__(self) -> str:
        return self.remote_path


@dataclass
class Plugin(_Common):
    name: str
    disabled: bool
    jar_files: list[File]

    def __init__(
        self,
        cfg: ConfigParser,
        section_name: str,
        local_root: Path,
        remote_root: str,
    ) -> None:
        assert section_name.startswith("plugin:")
        self.name = section_name.removeprefix("plugin:")
        local_path = local_root / f"plugins/{self.name}"
        remote_path = f"{remote_root}/plugins/{self.name}"
        super().__init__(cfg, section_name, local_path, remote_path)
        self.disabled = cfg.getboolean(section_name, "disabled", fallback=False)
        self.jar_files = [
            File(name=f, local_path=local_path, remote_path=remote_path)
            for f in re.split(r"\s+", cfg[section_name].get("jars", fallback=""))
            if f
        ]
        self.jar_files.append(
            File(
                name=f"{self.name}.jar",
                local_path=local_path,
                remote_path=remote_path,
            )
        )

    def __repr__(self) -> str:
        return self.name


class Instance:
    def __init__(self, ini_file: Path) -> None:
        from core import Error

        if not ini_file.exists():
            raise Error(f"failed to find {ini_file.name}")

        cfg = ConfigParser()
        with ini_file.open() as f:
            cfg.read_file(f)

        self.name = ini_file.stem
        self.instances_path = Path.cwd() / "instances"
        self.instance_path = self.instances_path / self.name

        self.server = Server(cfg, self.instance_path, "/home/kidzone/opt")

        self.instances_path = self.instances_path
        self.root_path = self.instance_path
        self.jars_path = self.instance_path / "jars"
        self.plugins_path = self.instance_path / "plugins"
        self.mtimes = {}

        self.plugins = {}
        for section_name in [s for s in cfg.sections() if s.startswith("plugin:")]:
            plugin = Plugin(
                cfg,
                section_name,
                self.instance_path,
                self.server.remote_path,
            )
            self.plugins[plugin.name] = plugin

        self.links = []
        for section_name in [s for s in cfg.sections() if s.startswith("link:")]:
            self.links.append(Link(cfg, section_name, self.instance_path))

        self.replacements = []
        for section_name in [s for s in cfg.sections() if s.startswith("replace:")]:
            self.replacements.append(Replace(cfg, section_name, self.instance_path))

        self.jars_path.mkdir(parents=True, exist_ok=True)
        self.plugins_path.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return self.name
