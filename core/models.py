"""Modelos de datos."""
from dataclasses import dataclass, field, fields


@dataclass
class Game:
    id: int = 0
    name: str = ""
    platform: str = "other"          # steam, epic, ubisoft, ea, gog, other...
    exe_path: str = ""
    launch_uri: str = ""
    install_dir: str = ""
    process_name: str = ""           # nombre del .exe a vigilar para contar horas
    cover_path: str = ""
    external_id: str = ""            # appid de Steam, AppName de Epic...
    tags: str = ""                   # separadas por comas
    favorite: int = 0
    notes: str = ""
    source: str = "manual"           # manual | auto
    installed: int = 1               # 0 = lo posees pero no está instalado
    added_at: str = ""
    # Campos calculados por la consulta (no son columnas)
    total_seconds: int = 0
    sessions: int = 0
    last_played: str = ""

    @classmethod
    def from_row(cls, row) -> "Game":
        data = dict(row)
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    @property
    def tag_list(self) -> list:
        return [t.strip() for t in self.tags.split(",") if t.strip()]


@dataclass
class DetectedGame:
    name: str
    platform: str
    external_id: str = ""
    exe_path: str = ""
    launch_uri: str = ""
    install_dir: str = ""
    process_name: str = ""
    tags: str = ""
    installed: bool = True           # False = juego de tu cuenta que aún no has instalado
