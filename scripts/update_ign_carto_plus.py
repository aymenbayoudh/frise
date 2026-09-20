#!/usr/bin/env python3
"""Fetch IGN ADMIN EXPRESS COG CARTO PLUS 2026 (DROM rapprochés) and extract
only the lightweight layers used by the national overview.

The product is download-only: it is not advertised by the public 2026 WFS.
This script discovers its current official GeoPackage URL through the
Géoplateforme download API, downloads it temporarily, reprojects the relocated
Lambert-93 geometries to EPSG:4326 for Leaflet, then commits only derived
GeoJSON/JSON files. The raw GeoPackage is never committed.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import requests

from update_ign_admin import normalize_geo, write_json, write_pretty

CAPABILITIES = "https://data.geopf.fr/telechargement/capabilities"
OUT = Path("carto/data/ign/2026/overview")
TIMEOUT = 120

session = requests.Session()
session.headers.update({
    "User-Agent": "frise-carto-admin-express/1.0 (+https://github.com/aymenbayoudh/frise)",
    "Accept": "application/json",
})


def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = session.get(url, params=params, timeout=TIMEOUT, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def entries_all(url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    params = dict(params or {})
    params.setdefault("limit", 50)
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        params["page"] = page
        data = get_json(url, params)
        chunk = data.get("entry") or []
        out.extend(chunk)
        total = int(data.get("totalentries") or len(out))
        if not chunk or len(out) >= total:
            break
        page += 1
    return out


def blob(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False).upper()


def links(obj: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in obj.get("link") or []:
        href = item.get("href") if isinstance(item, dict) else None
        if href:
            out.append(str(href))
    value = obj.get("id")
    if isinstance(value, str) and value.startswith("http"):
        out.append(value)
    return list(dict.fromkeys(out))


def discover_gpkg() -> tuple[str, dict[str, Any]]:
    # CARTO PLUS is an official download-only resource and is absent from the
    # public 2026 WFS. GetCapabilities currently exposes this stable resource id.
    resource_url = "https://data.geopf.fr/telechargement/resource/ADMIN-EXPRESS-COG-CARTOPLUS"
    filters = {
        "lang": "fre",
        "zone": "FRA",
        "format": "GPKG",
        "editionDateFrom": "2026-01-01",
        "editionDateTo": "2026-12-31",
    }
    try:
        subresources = entries_all(resource_url, filters)
    except Exception:
        subresources = entries_all(resource_url, {"lang": "fre"})

    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for sub in subresources:
        if "2026" not in blob(sub):
            continue
        sub_urls = [
            u.split("?", 1)[0] for u in links(sub)
            if "/telechargement/resource/ADMIN-EXPRESS-COG-CARTOPLUS/" in u
        ]
        for sub_url in sub_urls:
            try:
                files = entries_all(sub_url, {"lang": "fre"})
            except Exception:
                continue
            for file_entry in files:
                for u in links(file_entry):
                    ub = u.upper()
                    if "/TELECHARGEMENT/DOWNLOAD/" not in ub or not (ub.endswith(".GPKG") or ub.endswith(".7Z")):
                        continue
                    if "2026" not in ub:
                        continue
                    score = 0
                    if "CARTOPLUS-SANS-ECHELLE" in ub or "SANS-ECHELLE" in ub or "SANS_ECHELLE" in ub:
                        score += 100
                    if "CARTOPLUS-AVEC-ECHELLE" in ub or "AVEC-ECHELLE" in ub or "AVEC_ECHELLE" in ub:
                        score += 20
                    if "2026-01-01" in ub or "ED2026-01-01" in ub:
                        score += 10
                    candidates.append((score, u, {
                        "resource_url": resource_url,
                        "subresource": sub,
                        "file": file_entry,
                    }))

    if not candidates:
        # Diagnostic: query the exact 2026 subresource and dump every returned
        # file entry. IGN's file packaging/name is not necessarily the title
        # shown on the product news page.
        sub = next((x for x in subresources if "2026-01-01" in blob(x)), None)
        detail = []
        if sub:
            sub_id = next((u for u in links(sub) if "/telechargement/resource/ADMIN-EXPRESS-COG-CARTOPLUS/" in u), "")
            if sub_id:
                try:
                    detail = entries_all(sub_id.split("?", 1)[0], {"lang": "fre"})
                except Exception as exc:
                    detail = [{"diagnostic_error": str(exc), "subresource_url": sub_id}]
        raise RuntimeError(
            "GeoPackage CARTO PLUS 2026 introuvable. Fichiers de la sous-ressource: "
            + json.dumps(detail[:20], ensure_ascii=False)[:12000]
        )
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, url, meta = candidates[0]
    return url, meta


def download(url: str, dest: Path) -> None:
    with session.get(url, stream=True, timeout=300, headers={"Accept": "*/*"}) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    fh.write(chunk)


def layer_names(gpkg: Path) -> list[str]:
    p = subprocess.run(["ogrinfo", "-ro", "-q", str(gpkg)], check=True, capture_output=True, text=True)
    out: list[str] = []
    for line in p.stdout.splitlines():
        m = re.match(r"\s*\d+:\s*(.+?)(?:\s+\([^)]*\))?\s*$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def fold(value: str) -> str:
    s = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def pick_layer(names: list[str], *wanted: str) -> str | None:
    wanted_f = {fold(x) for x in wanted}
    exact = [n for n in names if fold(n) in wanted_f]
    if exact:
        return exact[0]
    # Delivery layer names sometimes contain a short product prefix.
    for n in names:
        fn = fold(n)
        if any(fn.endswith("_" + w) or fn.endswith(w) for w in wanted_f):
            return n
    return None


def ogr_to_geojson(gpkg: Path, layer: str, tmp: Path) -> dict[str, Any]:
    subprocess.run([
        "ogr2ogr", "-overwrite", "-f", "GeoJSON",
        "-t_srs", "EPSG:4326",
        "-lco", "RFC7946=YES",
        "-lco", "COORDINATE_PRECISION=5",
        str(tmp), str(gpkg), layer,
    ], check=True)
    return json.loads(tmp.read_text(encoding="utf-8"))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    url, discovery = discover_gpkg()

    with tempfile.TemporaryDirectory(prefix="ign-carto-plus-") as td:
        td_path = Path(td)
        downloaded = td_path / ("carto-plus.7z" if url.lower().endswith(".7z") else "carto-plus.gpkg")
        download(url, downloaded)

        if downloaded.suffix.lower() == ".7z":
            extract_dir = td_path / "archive"
            extract_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["7z", "x", "-y", f"-o{extract_dir}", str(downloaded)], check=True)
            gpkg_candidates = list(extract_dir.rglob("*.gpkg"))
            if not gpkg_candidates:
                raise RuntimeError("L'archive CARTO PLUS ne contient aucun GeoPackage")
            def gpkg_score(path: Path) -> tuple[int, str]:
                name = path.name.upper()
                score = 0
                if "SANS-ECHELLE" in name or "SANS_ECHELLE" in name:
                    score += 100
                if "AVEC-ECHELLE" in name or "AVEC_ECHELLE" in name:
                    score += 20
                if "CARTOPLUS" in name:
                    score += 10
                return (score, name)
            gpkg = sorted(gpkg_candidates, key=gpkg_score, reverse=True)[0]
        else:
            gpkg = downloaded

        names = layer_names(gpkg)

        specs = {
            "regions": ("region",),
            "departements": ("departement",),
            "epci": ("epci", "epci3"),
            "arrondissements": ("arrondissement",),
            "collectivites": ("collectivite_territoriale",),
        }
        selected: dict[str, str] = {}
        counts: dict[str, int] = {}

        for output, wanted in specs.items():
            layer = pick_layer(names, *wanted)
            if not layer:
                continue
            raw = ogr_to_geojson(gpkg, layer, td_path / f"{output}.geojson")
            canonical = "epci" if output == "epci" else output.rstrip("s")
            geo = normalize_geo(raw, canonical)
            write_json(OUT / f"{output}.geojson", geo)
            selected[output] = layer
            counts[output] = len(geo.get("features") or [])

        commune_center_layer = pick_layer(names, "chef_lieu_de_commune")
        center_map: dict[str, list[float]] = {}
        if commune_center_layer:
            raw = ogr_to_geojson(gpkg, commune_center_layer, td_path / "commune-centers.geojson")
            normalized = normalize_geo(raw, "center")
            for feature in normalized.get("features") or []:
                props = feature.get("properties") or {}
                code = str(props.get("code") or "")
                geom = feature.get("geometry") or {}
                coords = geom.get("coordinates")
                if code and geom.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
                    center_map[code] = [round(float(coords[1]), 5), round(float(coords[0]), 5)]
            write_json(OUT / "commune-centers.json", center_map)
            selected["commune_centers"] = commune_center_layer
            counts["commune_centers"] = len(center_map)

        manifest = {
            "source": "IGN ADMIN EXPRESS COG CARTO PLUS 2026",
            "variant": "sans conservation d'echelle des DROM",
            "download_url": url,
            "geopackage_file": gpkg.name,
            "available_layers": names,
            "selected_layers": selected,
            "counts": counts,
            "download_discovery": discovery,
        }
        write_pretty(OUT / "manifest.json", manifest)

    print(json.dumps({"download_url": url, "selected_layers": selected, "counts": counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
