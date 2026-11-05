"""Copias de seguridad, comprobación de integridad y restauración de la base de datos."""
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from utils.logger import get_logger
from utils.paths import data_dir

log = get_logger("backup")
PREFIX = "gamesword_backup_"


class BackupError(Exception):
    pass


def backups_dir() -> Path:
    p = data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def check_integrity(db_path: Path) -> Tuple[bool, str]:
    """(ok, mensaje). Un archivo inexistente cuenta como correcto (se creará nuevo)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return True, "sin base de datos todavía"
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
        return (row[0] == "ok"), str(row[0])
    except sqlite3.Error as exc:
        return False, str(exc)


def list_backups() -> List[Path]:
    return sorted(backups_dir().glob(f"{PREFIX}*.zip"), reverse=True)


def create_backup(db_path: Path, settings, version: str = "", keep: int = 7) -> Path:
    """Crea un .zip con la base de datos (copia consistente) y los ajustes SIN claves."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise BackupError("Todavía no hay datos que guardar.")
    out = backups_dir() / f"{PREFIX}{datetime.now():%Y%m%d_%H%M%S}.zip"
    n = 1
    while out.exists():                                   # dos copias en el mismo segundo
        out = out.with_name(f"{out.stem}_{n}.zip")
        n += 1
    tmp = Path(tempfile.mkdtemp()) / "gamesword.db"
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)                               # copia consistente aunque la app esté usando la base
        finally:
            dst.close()
            src.close()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmp, "gamesword.db")
            z.writestr("settings.json", json.dumps(settings.export_public(), indent=2, ensure_ascii=False))
            z.writestr("manifest.json", json.dumps({"app": "gamesword", "version": version,
                                                     "created": datetime.now().isoformat(timespec="seconds")}))
    except (sqlite3.Error, OSError) as exc:
        out.unlink(missing_ok=True)
        raise BackupError(f"No se pudo crear la copia: {exc}")
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    for old in list_backups()[keep:]:
        old.unlink(missing_ok=True)
    settings.set("app.last_backup", datetime.now().isoformat(timespec="seconds"))
    log.info("Copia creada: %s", out.name)
    return out


def backup_due(settings, hours: int = 24) -> bool:
    if not settings.get("app.auto_backup", True):
        return False
    try:
        last = datetime.fromisoformat(settings.get("app.last_backup", ""))
    except (TypeError, ValueError):
        return True
    return datetime.now() - last > timedelta(hours=hours)


def restore_backup(zip_path: Path, db_path: Path, settings=None) -> Path:
    """Restaura la base de datos (y los ajustes públicos) desde una copia. Guarda antes la base actual."""
    zip_path, db_path = Path(zip_path), Path(db_path)
    try:
        with zipfile.ZipFile(zip_path) as z:
            if "gamesword.db" not in z.namelist():
                raise BackupError("El archivo no es una copia de Gamesword.")
            tmpdir = Path(tempfile.mkdtemp())
            z.extract("gamesword.db", tmpdir)
            public = json.loads(z.read("settings.json")) if "settings.json" in z.namelist() else None
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise BackupError(f"No se pudo leer la copia: {exc}")
    ok, msg = check_integrity(tmpdir / "gamesword.db")
    if not ok:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise BackupError(f"La copia está dañada ({msg}); no se ha restaurado nada.")
    safety = None
    if db_path.exists():
        safety = db_path.with_name(f"gamesword.db.antes_de_restaurar_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(db_path, safety)
    for suffix in ("-wal", "-shm"):
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    shutil.copy2(tmpdir / "gamesword.db", db_path)
    shutil.rmtree(tmpdir, ignore_errors=True)
    if settings is not None and public:
        settings.import_public(public)
    log.info("Copia restaurada desde %s", zip_path.name)
    return safety or db_path


def recover_if_corrupt(db_path: Path) -> Optional[str]:
    """Al arrancar: si la base está dañada, la aparta y restaura la copia más reciente válida.

    Devuelve un mensaje para el usuario, o None si todo estaba bien.
    """
    db_path = Path(db_path)
    ok, msg = check_integrity(db_path)
    if ok:
        return None
    log.error("Base de datos dañada: %s", msg)
    aside = db_path.with_name(f"gamesword.db.dañada_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.move(str(db_path), str(aside))
    for suffix in ("-wal", "-shm"):
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    for b in list_backups():
        try:
            restore_backup(b, db_path, None)
            return (f"La base de datos estaba dañada. Se ha restaurado la copia «{b.name}». "
                    f"El archivo dañado se guardó como {aside.name}.")
        except BackupError:
            continue
    return (f"La base de datos estaba dañada y no había copias válidas: se ha creado una nueva. "
            f"El archivo dañado se guardó como {aside.name}.")
