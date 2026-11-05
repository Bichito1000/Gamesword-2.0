"""Recomendaciones por contenido sobre el catálogo offline."""
from collections import Counter
from difflib import SequenceMatcher
from typing import Iterable, List, Optional

from utils.helpers import normalize
from .catalog import CATALOG, TAG_SYNONYMS


def find_in_catalog(title: str, threshold: float = 0.72) -> Optional[dict]:
    t = normalize(title)
    if not t:
        return None
    best, best_score = None, 0.0
    for entry in CATALOG:
        n = normalize(entry["name"])
        if t == n:
            return entry
        score = SequenceMatcher(None, t, n).ratio()
        # "gta v", "gta 5" -> contenido parcial / siglas
        if t in n or n in t:
            score = max(score, 0.85)
        initials = "".join(w[0] for w in n.split())
        if t.replace(" ", "") == initials:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = entry, score
    # alias frecuentes
    aliases = {"gta": "Grand Theft Auto V", "gta v": "Grand Theft Auto V", "gta 5": "Grand Theft Auto V",
               "cs2": "Counter-Strike 2", "csgo": "Counter-Strike 2", "lol": "League of Legends",
               "rdr2": "Red Dead Redemption 2", "fifa": "FIFA / EA Sports FC", "r6": "Rainbow Six Siege",
               "rainbow six": "Rainbow Six Siege", "witcher": "The Witcher 3: Wild Hunt",
               "cyberpunk": "Cyberpunk 2077", "skyrim": "Skyrim Special Edition", "apex": "Apex Legends",
               "pubg": "PUBG: Battlegrounds", "wow": None}
    if t in aliases and aliases[t]:
        return next(e for e in CATALOG if e["name"] == aliases[t])
    return best if best_score >= threshold else None


def _owned_set(owned_names: Iterable[str]) -> set:
    return {normalize(n) for n in owned_names}


_WEIGHTS = {"multijugador": 0.35, "cooperativo": 0.5, "competitivo": 0.5, "familiar": 0.5,
            "indie": 0.5, "esports": 0.4, "mundo abierto": 1.6, "accion": 1.2, "narrativa": 0.8}


def _jaccard(a: set, b: set) -> float:
    """Jaccard ponderado: los géneros pesan más que 'multijugador' o 'indie'."""
    w = lambda tags: sum(_WEIGHTS.get(t, 1.0) for t in tags)
    union = w(a | b)
    return w(a & b) / union if union else 0.0


def similar_to(entry: dict, n: int = 5, owned_names: Iterable[str] = ()) -> List[dict]:
    owned = _owned_set(owned_names)
    base = set(entry["tags"])
    scored = []
    for other in CATALOG:
        if other["name"] == entry["name"] or normalize(other["name"]) in owned:
            continue
        shared = base & set(other["tags"])
        score = _jaccard(base, set(other["tags"])) + (0.08 if other["coop"] == entry["coop"] else 0)
        if score > 0:
            scored.append((score, other, shared))
    scored.sort(key=lambda x: -x[0])
    return [dict(o, reason="Comparte " + ", ".join(sorted(s)[:3])) for _, o, s in scored[:n]]


def tags_from_text(text: str) -> List[str]:
    t = normalize(text)
    found = []
    for tag, words in TAG_SYNONYMS.items():
        if any(normalize(w) in t for w in words):
            found.append(tag)
    return found


def by_tags(tags: List[str], n: int = 6, owned_names: Iterable[str] = ()) -> List[dict]:
    owned = _owned_set(owned_names)
    want = set(tags)
    exact, partial = [], []
    for g in CATALOG:
        if normalize(g["name"]) in owned:
            continue
        gtags = set(g["tags"])
        if "cooperativo" in want and not g["coop"]:
            continue
        hit = want & gtags
        if not hit:
            continue
        item = (len(hit) / len(want), g, hit)
        (exact if hit == want else partial).append(item)
    exact.sort(key=lambda x: x[1]["name"])
    partial.sort(key=lambda x: (-x[0], x[1]["name"]))
    chosen = exact if len(exact) >= 3 else exact + partial
    return [dict(g, reason="Encaja con: " + ", ".join(sorted(h))) for _, g, h in chosen[:n]]


def for_user(games, n: int = 8) -> List[dict]:
    """`games`: lista de Game ordenada de más a menos jugado."""
    owned = [g.name for g in games]
    counter = Counter()
    for g in games[:12]:
        entry = find_in_catalog(g.name, 0.8)
        tags = entry["tags"] if entry else g.tag_list
        weight = max(g.total_seconds / 3600, 0.5)
        for t in tags:
            if t not in ("multijugador",):
                counter[t] += weight
    if not counter:
        # Sin datos: populares variados
        pool = [e for e in CATALOG if normalize(e["name"]) not in _owned_set(owned)]
        return [dict(e, reason="Un clásico para empezar") for e in pool[:n]]
    top_tags = [t for t, _ in counter.most_common(4)]
    owned_set = _owned_set(owned)
    scored = []
    for g in CATALOG:
        if normalize(g["name"]) in owned_set:
            continue
        s = sum(counter.get(t, 0) for t in g["tags"])
        if s > 0:
            scored.append((s, g))
    scored.sort(key=lambda x: -x[0])
    return [dict(g, reason="Por tu afición a " + ", ".join(top_tags[:2])) for _, g in scored[:n]]
