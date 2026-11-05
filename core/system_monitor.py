"""Monitor de rendimiento y «modo gaming» (solo lectura salvo acciones confirmadas por el usuario)."""
import os
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

import psutil

from utils.logger import get_logger

log = get_logger("monitor")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROTECTED = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "sihost.exe",
    "taskhostw.exe", "ctfmon.exe", "audiodg.exe", "memory compression", "searchhost.exe", "startmenuexperiencehost.exe",
    "python.exe", "pythonw.exe", "gamesword.exe", "nvcontainer.exe", "msmpeng.exe", "securityhealthservice.exe",
}
HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED = "381b4222-f694-41f0-9685-bb19fc5b1500"
_GUID = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")


def gpu_info() -> Optional[Dict]:
    """GPU NVIDIA vía nvidia-smi (si está instalado). Otras marcas: no disponible."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4, creationflags=_NO_WINDOW).stdout.strip().splitlines()
        name, util, temp, used, total = [x.strip() for x in out[0].split(",")]
        return {"name": name, "util": float(util), "temp": float(temp), "mem_used": float(used),
                "mem_total": float(total)}
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def snapshot() -> Dict:
    vm = psutil.virtual_memory()
    return {"cpu": psutil.cpu_percent(interval=None), "ram": vm.percent,
            "ram_used": vm.used / 1024 ** 3, "ram_total": vm.total / 1024 ** 3, "gpu": gpu_info()}


def describe(snap: Dict) -> str:
    text = (f"CPU al {snap['cpu']:.0f} %, RAM al {snap['ram']:.0f} % "
            f"({snap['ram_used']:.1f} de {snap['ram_total']:.1f} GB).")
    g = snap.get("gpu")
    if g:
        text += (f" GPU {g['name']}: {g['util']:.0f} % de uso, {g['temp']:.0f} °C, "
                 f"{g['mem_used']:.0f}/{g['mem_total']:.0f} MB de VRAM.")
    else:
        text += " (No detecto una GPU NVIDIA, así que no puedo medir la gráfica.)"
    return text


def top_processes(n: int = 8) -> List[Dict]:
    """Procesos que más RAM usan, agrupados por nombre."""
    groups: Dict[str, Dict] = {}
    me = os.getpid()
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = p.info["name"] or "?"
            mem = p.info["memory_info"].rss if p.info["memory_info"] else 0
        except (psutil.Error, OSError):
            continue
        g = groups.setdefault(name, {"name": name, "pids": [], "mb": 0.0})
        g["pids"].append(p.info["pid"])
        g["mb"] += mem / 1024 ** 2
        if p.info["pid"] == me:
            g["self"] = True
    rows = [g for g in groups.values() if g["name"].lower() not in PROTECTED and not g.get("self")]
    rows.sort(key=lambda g: -g["mb"])
    return rows[:n]


def is_protected(name: str) -> bool:
    return name.lower() in PROTECTED


def close_processes(name: str, pids: List[int]) -> int:
    """Cierra (terminate, no kill) los procesos de la lista. Devuelve cuántos se pidió cerrar."""
    if is_protected(name):
        return 0
    n = 0
    for pid in pids:
        try:
            psutil.Process(pid).terminate()
            n += 1
        except (psutil.Error, OSError):
            continue
    return n


def active_power_plan() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=5,
                             creationflags=_NO_WINDOW).stdout
        m = _GUID.search(out)
        return m.group(0).lower() if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def set_power_plan(guid: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        r = subprocess.run(["powercfg", "/setactive", guid], capture_output=True, timeout=5,
                           creationflags=_NO_WINDOW)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def disks() -> List[Dict]:
    out = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts.lower() or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (OSError, PermissionError):
            continue
        out.append({"mount": part.mountpoint, "free_gb": u.free / 1024 ** 3, "total_gb": u.total / 1024 ** 3,
                    "percent": u.percent})
    return out


def diagnose() -> str:
    """Resumen legible con avisos concretos (no inventa nada: solo lo que se puede medir)."""
    psutil.cpu_percent(interval=None)
    snap = snapshot()
    snap["cpu"] = psutil.cpu_percent(interval=0.6)       # medida real durante unos instantes
    findings, ok = [], []
    if snap["cpu"] >= 90:
        findings.append(f"La CPU está al {snap['cpu']:.0f} %: hay algo consumiéndola.")
    else:
        ok.append(f"CPU {snap['cpu']:.0f} %")
    if snap["ram"] >= 85:
        findings.append(f"La RAM está al {snap['ram']:.0f} % ({snap['ram_used']:.1f} de {snap['ram_total']:.1f} GB): "
                        "cierra programas pesados antes de jugar.")
    else:
        ok.append(f"RAM {snap['ram']:.0f} %")
    g = snap.get("gpu")
    if g:
        if g["temp"] >= 85:
            findings.append(f"La GPU está a {g['temp']:.0f} °C: revisa la ventilación o limita los FPS.")
        if g["mem_total"] and g["mem_used"] / g["mem_total"] >= 0.9:
            findings.append("La memoria de vídeo está casi llena: baja la calidad de texturas.")
        ok.append(f"GPU {g['util']:.0f} % ({g['temp']:.0f} °C)")
    for d in disks():
        if d["free_gb"] < 20 or d["percent"] >= 92:
            findings.append(f"A la unidad {d['mount']} le quedan solo {d['free_gb']:.0f} GB libres: los juegos y "
                            "las actualizaciones pueden fallar o ir lentos.")
    top = top_processes(3)
    text = "**Diagnóstico del PC**\n"
    text += ("\n".join("⚠️ " + f for f in findings) if findings else "✅ No veo ningún problema ahora mismo.")
    text += "\nMedido: " + ", ".join(ok) + "."
    if top:
        text += "\nLo que más memoria usa: " + ", ".join(f"{t['name']} ({t['mb']:.0f} MB)" for t in top) + "."
    if not g:
        text += "\n(No detecto una GPU NVIDIA, así que no puedo medir la gráfica ni sus temperaturas.)"
    return text
