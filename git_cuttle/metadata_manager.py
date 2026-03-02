import os
from dataclasses import dataclass, field
from pathlib import Path


def default_metadata_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "gitcuttle" / "workspaces.json"
    return Path.home() / ".local" / "share" / "gitcuttle" / "workspaces.json"


@dataclass(kw_only=True)
class MetadataManager:
    path: Path = field(default_factory=default_metadata_path)

    def ensure_parent_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
