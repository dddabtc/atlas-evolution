from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import textwrap
import tomllib


@dataclass(frozen=True, slots=True)
class PathConfig:
    config_file: Path
    skills_dir: Path
    state_dir: Path


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    top_k_skills: int = 3
    min_evidence: int = 2
    approval_threshold: float = 0.65
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True, slots=True)
class AtlasConfig:
    paths: PathConfig
    runtime: RuntimeConfig


def _resolve(base_dir: Path, raw_path: str, fallback: str) -> Path:
    path = Path(raw_path or fallback)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def load_config(path: str | Path) -> AtlasConfig:
    config_path = Path(path).expanduser().resolve()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent
    path_data = data.get("paths", {})
    runtime_data = data.get("runtime", {})
    paths = PathConfig(
        config_file=config_path,
        skills_dir=_resolve(base_dir, path_data.get("skills_dir", "skills"), "skills"),
        state_dir=_resolve(base_dir, path_data.get("state_dir", "state"), "state"),
    )
    runtime = RuntimeConfig(
        top_k_skills=int(runtime_data.get("top_k_skills", 3)),
        min_evidence=int(runtime_data.get("min_evidence", 2)),
        approval_threshold=float(runtime_data.get("approval_threshold", 0.65)),
        host=str(runtime_data.get("host", "127.0.0.1")),
        port=int(runtime_data.get("port", 8765)),
    )
    return AtlasConfig(paths=paths, runtime=runtime)


def default_config_text() -> str:
    return textwrap.dedent(
        """
        [paths]
        skills_dir = "skills"
        state_dir = "state"

        [runtime]
        top_k_skills = 3
        min_evidence = 2
        approval_threshold = 0.65
        host = "127.0.0.1"
        port = 8765
        """
    ).strip() + "\n"


def write_default_config(path: str | Path, overwrite: bool = False) -> Path:
    target = Path(path).expanduser().resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing config: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(default_config_text(), encoding="utf-8")
    return target
