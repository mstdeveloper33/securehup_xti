"""Explicit runtime paths; importing this module never creates files."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @property
    def database(self) -> Path:
        return self.data_dir / "xti.db"

    @classmethod
    def from_path(cls, path: str | Path) -> "Settings":
        return cls(data_dir=Path(path).expanduser().resolve())

