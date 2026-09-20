#!/usr/bin/env python3
"""
Build a local, browser-friendly extract of IGN ADMIN EXPRESS COG 2026 from the
official Géoplateforme WFS.

The script keeps only attributes used by carto/index.html and splits communes
by department so the browser never has to load all communes at once. It also
tries to discover the CARTO PLUS Petite Échelle product used for the compact
France + outre-mer overview.

Generated files are committed by the GitHub Actions workflow.
Source: IGN / Géoplateforme, Licence Ouverte 2.0.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

WFS = "https://data.geopf.fr/wfs/ows"
OUT = Path("carto/data/ign/2026")
PAGE_SIZE = 5000
TIMEOUT = 90

session = requests.Session()
session.headers.update({
    "User-Agent": "frise-carto-admin-express/1.0 (+https://github.com/aymenbayoudh/frise)"
})


def request(url: str, params: dict[str, Any] | None = None, *, tries: int = 5) -> requests.Response:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = session.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            if attempt + 1 < tries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed: {url} {params or ''}") from last


def capabilities() -> list[str]:
    r = request(WFS, {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetCapabilities",
    })
    root = ET.fromstring(r.content)
    names: list[str] = []
    for el in root.iter():
        if el.tag.endswith("FeatureType"):
            for child in list(el):
                if child.tag.endswith("Name") and child.text:
                    names.append(child.text.strip())
                    break
    return sorted(set(names))


def download_capabilities_carto_plus() -> list[str]:
    """Return unique text/attribute values around CARTO PLUS download entries.

    The download service is XML and its schema can evolve. Keeping a small
    discovery snapshot lets the build adapt without hard-coding a guessed URL.
    """
    url = "https://data.geopf.fr/telechargement/capabilities"
    try:
        r = request(url)
        root = ET.fromstring(r.content)
    except Exception as e:
        return [f"ERROR: {e}"]

    values: set[str] = set()
    for el in root.iter():
        blob = " ".join(
            [str(el.tag), str(el.text or "")]
            + [f"{k}={v}" for k, v in el.attrib.items()]
            + [str(ch.text or "") for ch in list(el)]
        )
        if "CARTOPLUS" not in blob.upper() and "CARTO_PLUS" not in blob.upper() and "CARTO PLUS" not in blob.upper():
            continue
        for node in el.iter():
            if node.text and node.text.strip():
                values.add(node.text.strip())
            for k, v in node.attrib.items():
                values.add(f"{k}={v}")
    return sorted(values)


def suffix(name: str) -> str:
    return name.split(":", 1)[-1].lower()


def prefix(name: str) -> str:
    return name.split(":", 1)[0].upper()


def product_score(name: str, *, overview: bool) -> int:
    p = prefix(name)
    score = 0
    if "2026" in p:
        score += 1000
    if overview:
        if "PLUS" in p or "CARTOPLUS" in p or "CARTO_PLUS" in p:
            score += 500
        if "PE" in p:
            score += 80
    else:
        # Browser display: prefer the official small-scale COG CARTO PE geometry.
        # It is much lighter than the full-detail COG while remaining the same
        # 2026 IGN administrative reference. Full-detail COG is only a fallback.
        if "COG-CARTO-PE.2026" in p:
            score += 500
        if "COG-CARTO.2026" in p:
            score += 420
        if "ADMINEXPRESS-COG.2026" in p or "ADMIN-EXPRESS-COG.2026" in p:
            score += 300
        if "LATEST" in p:
            score += 20
    return score


def find_layer(
    names: Iterable[str],
    wanted: str | tuple[str, ...],
    *,
    overview: bool,
    required: bool = True,
) -> str | None:
    wanted_set = {wanted} if isinstance(wanted, str) else set(wanted)
    wanted_set = {w.lower() for w in wanted_set}
    candidates = [n for n in names if suffix(n) in wanted_set]
    if overview:
        candidates = [n for n in candidates if ("PLUS" in prefix(n) or "CARTOPLUS" in prefix(n) or "CARTO_PLUS" in prefix(n))]
    else:
        candidates = [n for n in candidates if not ("PLUS" in prefix(n) or "CARTOPLUS" in prefix(n) or "CARTO_PLUS" in prefix(n))]
    candidates.sort(key=lambda n: (product_score(n, overview=overview), n), reverse=True)
    if candidates:
        return candidates[0]
    if required:
        raise RuntimeError(f"No WFS layer found for {wanted!r} (overview={overview})")
    return None


def fetch_geojson(type_name: str, *, page_size: int = PAGE_SIZE) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "OUTPUTFORMAT": "application/json",
            "SRSNAME": "EPSG:4326",
            "TYPENAMES": type_name,
            "COUNT": page_size,
            "STARTINDEX": start,
        }
        r = request(WFS, params)
        try:
            page = r.json()
        except Exception as e:
            raise RuntimeError(f"Invalid GeoJSON for {type_name} page {start}") from e
        chunk = page.get("features") or []
        features.extend(chunk)
        print(f"{type_name}: {len(features)} feature(s)", flush=True)
        if len(chunk) < page_size:
            break
        start += len(chunk)
        if not chunk:
            break
    return {"type": "FeatureCollection", "features": features}


def fold_key(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def prop_lookup(props: dict[str, Any]) -> dict[str, Any]:
    return {fold_key(k): v for k, v in props.items()}


def first(props: dict[str, Any], *keys: str) -> Any:
    p = prop_lookup(props)
    for k in keys:
        v = p.get(fold_key(k))
        if v is not None and str(v).strip() != "":
            return v
    return None


def derive_department(code: str) -> str:
    code = str(code or "").upper()
    if code.startswith(("2A", "2B")):
        return code[:2]
    if re.match(r"^(97|98)\d", code):
        return code[:3]
    return code[:2]


def normalize_feature(feature: dict[str, Any], layer: str) -> dict[str, Any]:
    props = feature.get("properties") or {}
    fid = str(feature.get("id") or "")

    if layer == "epci":
        code = first(props, "code_siren", "siren", "code_epci", "siren_epci", "code")
    else:
        code = first(props, "code_insee", "code", "insee", "insee_com", "insee_dep", "insee_reg")
    if code is None and "." in fid:
        code = fid.rsplit(".", 1)[-1]

    name = first(props, "nom_officiel", "nom", "libelle", "name", "nom_usage")
    dept = first(
        props,
        "code_insee_du_departement",
        "code_insee_departement",
        "code_departement",
        "departement",
        "code_dep",
        "dep",
    )
    region = first(
        props,
        "code_insee_de_la_region",
        "code_insee_region",
        "code_region",
        "region",
        "code_reg",
        "reg",
    )
    epci = first(
        props,
        "code_siren_de_l_epci",
        "code_siren_epci",
        "siren_epci",
        "code_epci",
    )
    chef = first(
        props,
        "code_insee_du_chef_lieu",
        "code_chef_lieu",
        "chef_lieu",
    )

    code_s = "" if code is None else str(code)
    if layer == "commune" and not dept:
        dept = derive_department(code_s)

    out_props: dict[str, Any] = {}
    if code_s:
        out_props["code"] = code_s
    if name is not None:
        out_props["nom"] = str(name)
    if dept is not None:
        out_props["departement"] = str(dept)
    if region is not None:
        out_props["region"] = str(region)
    if epci is not None:
        out_props["epci"] = str(epci)
    if chef is not None:
        out_props["chef_lieu"] = str(chef)

    siret = first(props, "siret")
    if siret is not None:
        out_props["siret"] = str(siret)

    return {
        "type": "Feature",
        "properties": out_props,
        "geometry": feature.get("geometry"),
    }


def normalize_geo(geo: dict[str, Any], layer: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [normalize_feature(f, layer) for f in geo.get("features") or [] if f.get("geometry")],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def write_pretty(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_standard(names: list[str]) -> dict[str, Any]:
    base = OUT / "geographic"
    layer_specs = {
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

    for out_name, wanted in layer_specs.items():
        layer = find_layer(names, wanted, overview=False)
        assert layer
        selected[out_name] = layer
        canonical = {
            "epci": "epci",
            "arrondissements": "arrondissement",
            "arrondissements_municipaux": "arrondissement",
            "communes_associees_deleguees": "commune",
            "collectivites": "collectivite",
        }.get(out_name, out_name.rstrip("s"))
        geo = normalize_geo(fetch_geojson(layer), canonical)
        write_json(base / f"{out_name}.geojson", geo)
        counts[out_name] = len(geo["features"])

    commune_layer = find_layer(names, "commune", overview=False)
    assert commune_layer
    selected["communes"] = commune_layer
    communes = normalize_geo(fetch_geojson(commune_layer), "commune")
    by_dept: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in communes["features"]:
        dept = str((f.get("properties") or {}).get("departement") or "")
        if dept:
            by_dept[dept].append(f)
    commune_dir = base / "communes"
    commune_dir.mkdir(parents=True, exist_ok=True)
    for old in commune_dir.glob("*.geojson"):
        old.unlink()
    for dept, features in sorted(by_dept.items()):
        write_json(commune_dir / f"{dept}.geojson", {"type": "FeatureCollection", "features": features})
    counts["communes"] = len(communes["features"])
    counts["commune_departments"] = len(by_dept)

    center_names = [n for n in names if prefix(n) == prefix(commune_layer) and suffix(n).startswith("chef_lieu")]
    if not center_names:
        center_names = [
            n for n in names
            if suffix(n).startswith("chef_lieu")
            and "2026" in prefix(n)
            and not ("PLUS" in prefix(n) or "CARTOPLUS" in prefix(n))
        ]
    center_features: list[dict[str, Any]] = []
    for layer in sorted(center_names):
        kind = suffix(layer)
        geo = fetch_geojson(layer)
        for f in geo.get("features") or []:
            nf = normalize_feature(f, "center")
            nf["properties"]["kind"] = kind
            center_features.append(nf)
    if center_features:
        write_json(base / "centers.geojson", {"type": "FeatureCollection", "features": center_features})
    counts["centers"] = len(center_features)
    selected["centers"] = sorted(center_names)

    return {"layers": selected, "counts": counts}


def build_overview(names: list[str]) -> dict[str, Any]:
    base = OUT / "overview"
    available = [n for n in names if "2026" in prefix(n) and ("PLUS" in prefix(n) or "CARTOPLUS" in prefix(n) or "CARTO_PLUS" in prefix(n))]
    if not available:
        return {"available": False, "reason": "No CARTO PLUS 2026 WFS layer advertised", "layers": {}, "counts": {}}

    specs = {
        "regions": ("region",),
        "departements": ("departement",),
        "epci": ("epci", "epci3"),
        "arrondissements": ("arrondissement",),
    }
    selected: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for out_name, wanted in specs.items():
        layer = find_layer(names, wanted, overview=True, required=False)
        if not layer:
            continue
        selected[out_name] = layer
        canonical = "epci" if out_name == "epci" else out_name.rstrip("s")
        geo = normalize_geo(fetch_geojson(layer), canonical)
        write_json(base / f"{out_name}.geojson", geo)
        counts[out_name] = len(geo["features"])

    center_names = [n for n in available if suffix(n).startswith("chef_lieu")]
    center_features: list[dict[str, Any]] = []
    for layer in sorted(center_names):
        kind = suffix(layer)
        geo = fetch_geojson(layer)
        for f in geo.get("features") or []:
            nf = normalize_feature(f, "center")
            nf["properties"]["kind"] = kind
            center_features.append(nf)
    if center_features:
        write_json(base / "centers.geojson", {"type": "FeatureCollection", "features": center_features})
    counts["centers"] = len(center_features)
    selected["centers"] = sorted(center_names)

    return {"available": bool(selected), "layers": selected, "counts": counts}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    names = capabilities()
    discovery = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wfs": WFS,
        "download_carto_plus": download_capabilities_carto_plus(),
        "matching_2026_admin_layers": [
            n for n in names if "2026" in n.upper() and ("ADMIN" in n.upper() or "LIMITE" in n.upper())
        ],
        "carto_plus_candidates": [
            n for n in names if "2026" in n.upper() and ("PLUS" in n.upper() or "CARTOPLUS" in n.upper())
        ],
    }
    write_pretty(OUT / "discovery.json", discovery)

    standard = build_standard(names)
    overview = build_overview(names)
    manifest = {
        "source": "IGN ADMIN EXPRESS COG 2026",
        "license": "Licence Ouverte / Open Licence 2.0",
        "wfs": WFS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "geographic": standard,
        "overview": overview,
    }
    write_pretty(OUT / "manifest.json", manifest)

    readme = """# IGN ADMIN EXPRESS COG 2026

Generated automatically from the official IGN Géoplateforme WFS by scripts/update_ign_admin.py.

- geographic/: true geographic geometry used after entering a territory.
- overview/: CARTO PLUS Petite Échelle geometry, when exposed by the WFS, used only for the compact national overview with overseas territories moved next to mainland France.
- geographic/communes/: one GeoJSON per department, loaded on demand.
- manifest.json: exact official WFS layer names and feature counts used for the build.
- discovery.json: 2026 WFS layer discovery snapshot, useful if IGN renames a service.

Source: IGN — ADMIN EXPRESS COG 2026. Licence Ouverte 2.0.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
