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


def ogr_to_geojson(gpkg: Path, layer: str, tmp: Path, *, simplify: float | None = None) -> dict[str, Any]:
    args = [
        "ogr2ogr", "-overwrite", "-f", "GeoJSON",
        "-t_srs", "EPSG:4326",
        "-lco", "RFC7946=YES",
        "-lco", "COORDINATE_PRECISION=5",
    ]
    # CARTO PLUS is only shown in the compact overview. A ~13 m tolerance on
    # EPCI borders stays below a screen pixel even at the overview handoff zoom,
    # while removing many redundant coastline/boundary vertices.
    if simplify and simplify > 0:
        args.extend(["-simplify", str(simplify)])
    args.extend([str(tmp), str(gpkg), layer])
    subprocess.run(args, check=True)
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
            "arrondissements_municipaux": ("arrondissement_municipal",),
            "collectivites": ("collectivite_territoriale",),
            "communes_associees_deleguees": ("commune_associee_ou_deleguee",),
        }
        selected: dict[str, Any] = {}
        counts: dict[str, int] = {}
        overview_epci_geo: dict[str, Any] | None = None

        for output, wanted in specs.items():
            layer = pick_layer(names, *wanted)
            if not layer:
                continue
            raw = ogr_to_geojson(
                gpkg,
                layer,
                td_path / f"{output}.geojson",
                simplify=0.00012 if output == "epci" else None,
            )
            canonical = {
                "epci": "epci",
                "arrondissements": "arrondissement",
                "arrondissements_municipaux": "arrondissement",
                "communes_associees_deleguees": "commune",
                "collectivites": "collectivite",
            }.get(output, output.rstrip("s"))
            geo = normalize_geo(raw, canonical)
            write_json(OUT / f"{output}.geojson", geo)
            if output == "epci":
                overview_epci_geo = geo
            selected[output] = layer
            counts[output] = len(geo.get("features") or [])

        def geometry_center(geometry: dict[str, Any] | None) -> list[float] | None:
            if not geometry:
                return None
            points: list[tuple[float, float]] = []
            def visit(value: Any) -> None:
                if isinstance(value, list) and len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
                    points.append((float(value[0]), float(value[1])))
                    return
                if isinstance(value, list):
                    for child in value:
                        visit(child)
            visit(geometry.get("coordinates"))
            if not points:
                return None
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return [round((min(ys) + max(ys)) / 2, 5), round((min(xs) + max(xs)) / 2, 5)]

        commune_center_layer = pick_layer(names, "chef_lieu_de_commune")
        center_map: dict[str, list[float]] = {}
        commune_name_map: dict[str, str] = {}
        if commune_center_layer:
            raw = ogr_to_geojson(gpkg, commune_center_layer, td_path / "commune-centers.geojson")
            normalized = normalize_geo(raw, "center")
            for feature in normalized.get("features") or []:
                props = feature.get("properties") or {}
                code = str(props.get("code") or "")
                name = str(props.get("nom") or "")
                at = geometry_center(feature.get("geometry"))
                if code and name:
                    commune_name_map[code] = name
                if code and at:
                    center_map[code] = at
            selected["commune_centers"] = commune_center_layer

        # Some CARTO PLUS centre layers do not expose the commune code in the
        # same field names as the polygon layer. Fall back to polygon bboxes:
        # this is only for positioning bubbles/labels in the relocated overview.
        if len(center_map) < 1000:
            commune_layer = pick_layer(names, "commune")
            if commune_layer:
                raw_communes = ogr_to_geojson(gpkg, commune_layer, td_path / "communes-for-centers.geojson")
                normalized_communes = normalize_geo(raw_communes, "commune")
                for feature in normalized_communes.get("features") or []:
                    code = str((feature.get("properties") or {}).get("code") or "")
                    at = geometry_center(feature.get("geometry"))
                    if code and at:
                        center_map.setdefault(code, at)
                selected["commune_centers_fallback"] = commune_layer

        write_json(OUT / "commune-centers.json", center_map)
        counts["commune_centers"] = len(center_map)

        # Dedicated official EPCI seats. The public CARTO-PE WFS currently
        # omits chef_lieu_d_epci, while the official CARTO PLUS GeoPackage
        # contains it. Keep a compact SIREN -> seat commune lookup for Carto.
        group_center_layer = pick_layer(names, "chef_lieu_d_epci")
        group_center_map: dict[str, dict[str, Any]] = {}
        # ADMIN EXPRESS locates the three large city EPCI seats inside a
        # municipal arrondissement. For Carto the relevant "ville-centre" is
        # the parent commune itself, not Paris 13e / Lyon 3e / Marseille 7e.
        parent_city_seats = {
            "200054781": ("75056", "Paris"),
            "200046977": ("69123", "Lyon"),
            "200054807": ("13055", "Marseille"),
        }
        if group_center_layer:
            raw = ogr_to_geojson(gpkg, group_center_layer, td_path / "group-centers.geojson")
            normalized = normalize_geo(raw, "center")
            for feature in normalized.get("features") or []:
                props = feature.get("properties") or {}
                siren = str(props.get("epci") or "")
                code = str(props.get("code") or "")
                # The EPCI chief-lieu feature name is an institutional label
                # ("Siège de ..."), not the municipality name shown on the map.
                name = commune_name_map.get(code) or str(props.get("nom") or code)
                at = geometry_center(feature.get("geometry"))
                if siren in parent_city_seats:
                    code, name = parent_city_seats[siren]
                    at = center_map.get(code) or at
                if re.fullmatch(r"\d{9}", siren) and code:
                    item: dict[str, Any] = {"code": code, "name": name}
                    if at:
                        item["at"] = at
                    group_center_map[siren] = item
            selected["group_centers"] = group_center_layer
        write_json(OUT / "group-centers.json", group_center_map)
        counts["group_centers"] = len(group_center_map)

        # Reconcile the detailed geographic EPCI layer with the same CARTO PLUS
        # 2026 membership used by chef_lieu_d_epci. The public CARTO-PE WFS can
        # lag behind mid-year intercommunal mergers: keep its real-world
        # geometries for unchanged EPCI, remove dissolved codes, and add only
        # missing current metropolitan geometries from CARTO PLUS.
        geographic_epci_path = OUT.parent / "geographic" / "epci.geojson"
        if geographic_epci_path.exists() and overview_epci_geo and group_center_map:
            geographic_epci = json.loads(geographic_epci_path.read_text(encoding="utf-8"))
            current_codes = set(group_center_map)
            geographic_features = geographic_epci.get("features") or []
            overview_by_code = {
                str((feature.get("properties") or {}).get("code") or ""): feature
                for feature in overview_epci_geo.get("features") or []
            }
            kept = [
                feature for feature in geographic_features
                if str((feature.get("properties") or {}).get("code") or "") in current_codes
            ]
            kept_codes = {
                str((feature.get("properties") or {}).get("code") or "")
                for feature in kept
            }
            missing_codes = sorted(current_codes - kept_codes)
            added_codes: list[str] = []
            for code in missing_codes:
                feature = overview_by_code.get(code)
                if not feature:
                    raise RuntimeError(f"EPCI CARTO PLUS {code} sans géométrie")
                seat_code = str(group_center_map[code].get("code") or "")
                if seat_code.startswith(("97", "98")):
                    raise RuntimeError(
                        f"EPCI ultramarin {code} absent du WFS : géométrie CARTO PLUS déplacée non utilisable"
                    )
                kept.append(feature)
                added_codes.append(code)
            removed_codes = sorted({
                str((feature.get("properties") or {}).get("code") or "")
                for feature in geographic_features
                if str((feature.get("properties") or {}).get("code") or "") not in current_codes
            })
            reconciled = {"type": "FeatureCollection", "features": kept}
            write_json(geographic_epci_path, reconciled)
            counts["epci_geographic"] = len(kept)

            root_manifest_path = OUT.parent / "manifest.json"
            if root_manifest_path.exists():
                root_manifest = json.loads(root_manifest_path.read_text(encoding="utf-8"))
                geographic_manifest = root_manifest.setdefault("geographic", {})
                geographic_manifest.setdefault("counts", {})["epci"] = len(kept)
                geographic_manifest["epci_reconciliation"] = {
                    "membership_source": group_center_layer,
                    "removed_codes": removed_codes,
                    "added_codes": added_codes,
                }
                write_pretty(root_manifest_path, root_manifest)

        # Keep every official chief-lieu class locally as well (including
        # chef_lieu_d_epci, which is present in CARTO PLUS even when absent from
        # the public CARTO-PE WFS capabilities).
        all_centers: list[dict[str, Any]] = []
        center_layers = [name for name in names if fold(name).startswith("chef_lieu")]
        for center_layer in center_layers:
            raw_center = ogr_to_geojson(gpkg, center_layer, td_path / ("center-" + fold(center_layer) + ".geojson"))
            for feature in raw_center.get("features") or []:
                nf = normalize_geo({"type": "FeatureCollection", "features": [feature]}, "center")["features"]
                if not nf:
                    continue
                item = nf[0]
                item["properties"]["kind"] = fold(center_layer)
                all_centers.append(item)
        if all_centers:
            write_json(OUT / "centers.geojson", {"type": "FeatureCollection", "features": all_centers})
        selected["centers"] = center_layers
        counts["centers"] = len(all_centers)

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
