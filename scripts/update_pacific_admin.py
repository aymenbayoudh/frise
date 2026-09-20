#!/usr/bin/env python3
"""Build browser-ready Pacific administrative layers for carto.

New Caledonia source: Government of New Caledonia / Géorep.
French Polynesia source: Tefenua administrative dataset.

The geographic files keep true WGS84 positions. Separate compact "overview"
files are generated for the national France view: NC is uniformly relocated,
while PF uses an archipelago cartogram so the islands remain legible.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from shapely import affinity
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

OUT = Path("carto/data/pacific")
IGN_COLLECTIVITIES = Path("carto/data/ign/2026/overview/collectivites.geojson")
NC_SERVICE = "https://services1.arcgis.com/TZcrgU6CIbqWt9Qv/arcgis/rest/services/limites_terrestres/FeatureServer"
PF_LAYER = "https://services.arcgis.com/L4H4rU26VyhEF588/ArcGIS/rest/services/D%C3%A9coupage_administratif/FeatureServer/0"
TIMEOUT = 120

session = requests.Session()
session.headers.update({"User-Agent": "frise-carto-pacific-admin/2.0 (+https://github.com/aymenbayoudh/frise)"})


def get_geojson(url: str, where: str = "1=1", out_fields: str = "*") -> dict[str, Any]:
    params = {"where": where, "outFields": out_fields, "returnGeometry": "true", "outSR": "4326", "f": "geojson"}
    r = session.get(url.rstrip("/") + "/query", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    if data.get("type") != "FeatureCollection":
        raise RuntimeError(f"Unexpected ArcGIS response from {url}")
    return data


def fold(value: Any) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def first(props: dict[str, Any], *names: str) -> Any:
    lookup = {fold(k): v for k, v in props.items()}
    for name in names:
        v = lookup.get(fold(name))
        if v is not None and str(v).strip() != "":
            return v
    return None


def clean_shape(g):
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = g.buffer(0)
    return g if not g.is_empty else None


def clean_geometry(geom):
    if not geom:
        return None
    g = clean_shape(shape(geom))
    return mapping(g) if g else None


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def feature(code: str, name: str, geom, **extra: Any) -> dict[str, Any] | None:
    g = clean_shape(geom if hasattr(geom, "geom_type") else shape(geom))
    if not g:
        return None
    props = {"code": str(code), "nom": str(name), **{k: v for k, v in extra.items() if v is not None}}
    return {"type": "Feature", "properties": props, "geometry": mapping(g)}


def fc(features):
    return {"type": "FeatureCollection", "features": [f for f in features if f and f.get("geometry")]}


def union_features(features, code: str, name: str, **extra):
    geoms = [shape(f["geometry"]) for f in features if f and f.get("geometry")]
    if not geoms:
        return None
    return feature(code, name, unary_union(geoms), **extra)


def representative_latlng(f):
    p = shape(f["geometry"]).representative_point()
    return [round(float(p.y), 6), round(float(p.x), 6)]


def merge_same(items, default_region: str, preserve=("subdivision_code", "subdivision_name")):
    grouped = {}
    for f in items:
        grouped.setdefault(f["properties"]["code"], []).append(f)
    out = []
    for code, parts in grouped.items():
        p0 = parts[0]["properties"]
        extra = {"region": default_region}
        for k in preserve:
            if p0.get(k) is not None:
                extra[k] = p0.get(k)
        u = union_features(parts, code, p0["nom"], **extra)
        if u:
            out.append(u)
    return out


NC_GROUPS = [
    ("NC-SIGN", "Syndicat intercommunal du Grand Nouméa (SIGN)", ["Nouméa", "Dumbéa", "Mont-Dore", "Païta"], "Nouméa"),
    ("NC-SIVMSUD", "SIVM Sud", ["Bourail", "Boulouparis", "Farino", "La Foa", "Moindou", "Sarraméa", "Thio"], "La Foa"),
    ("NC-SIVOMVKP", "SIVOM VKP", ["Voh", "Koné", "Pouembout"], "Koné"),
    ("NC-SIVMNORD", "SIVM Nord", ["Kaala-Gomen", "Koumac", "Poum"], "Koumac"),
    ("NC-SIVMCOTEEST", "SIVM de la Côte Est", ["Houaïlou", "Ponérihouen", "Poindimié", "Touho", "Hienghène", "Pouébo"], "Poindimié"),
]

PF_GROUPS = [
    ("200027688", "Communauté de communes des Îles Marquises (CODIM)", ["Fatu Hiva", "Hiva Oa", "Nuku Hiva", "Tahuata", "Ua Huka", "Ua Pou"], "Taiohae"),
    ("200031243", "Communauté de communes Hava'i", ["Huahine", "Maupiti", "Tahaa", "Taputapuatea", "Tumaraa", "Uturoa"], "Uturoa"),
    ("200094803", "Communauté de communes Tereheamanu", ["Hitiaa O Te Ra", "Papara", "Taiarapu Est", "Taiarapu Ouest", "Teva I Uta"], "Taravao"),
    ("200102358", "Communauté de communes Teporionu'u", ["Arue", "Papeete", "Pirae"], "Papeete"),
    ("200102366", "Communauté de communes Te Tama a Hiro", ["Rapa", "Rimatara", "Rurutu", "Tubuai"], "Tubuai"),
    ("934286501", "Communauté de communes Mihiroa-Havaiki", ["Arutua", "Fakarava", "Rangiroa"], "Rangiroa"),
    ("994270916", "Communauté de communes Hono Hau", ["Gambier", "Hao", "Hikueru", "Reao", "Tureia"], "Hao"),
]

# City/locality coordinates used only for administrative-centre labels.
POINTS = {
    "Nouméa": [-22.2758, 166.4580],
    "Koné": [-21.0590, 164.8650],
    "Wé": [-20.9160, 167.2640],
    "La Foa": [-21.7100, 165.8270],
    "Poindimié": [-20.9490, 165.3330],
    "Koumac": [-20.5620, 164.2840],
    "Papeete": [-17.5516, -149.5585],
    "Uturoa": [-16.7330, -151.4330],
    "Taiohae": [-8.9100, -140.1000],
    "Tubuai": [-23.3460, -149.4850],
    "Taravao": [-17.7330, -149.3160],
    "Rangiroa": [-14.9540, -147.6490],
    "Hao": [-18.0750, -140.9450],
}


def feature_name_map(features):
    return {fold(f["properties"]["nom"]): f for f in features}


def find_by_name(features, name):
    key = fold(name)
    by = feature_name_map(features)
    if key in by:
        return by[key]
    matches = [f for k, f in by.items() if key in k or k in key]
    return matches[0] if len(matches) == 1 else None


def assign_subdivision(geom, raw_subs):
    p = geom.representative_point()
    hits = []
    for s in raw_subs:
        sg = shape(s["geometry"])
        if sg.contains(p) or sg.intersects(p):
            hits.append(s)
    if not hits:
        return None
    hits.sort(key=lambda s: shape(s["geometry"]).area)
    return hits[0]


def pf_commune_code(props):
    raw = first(props, "com_id", "code", "id")
    if raw is None:
        return ""
    try:
        n = int(float(raw))
        return f"987{n:02d}" if n < 100 else str(n)
    except Exception:
        s = re.sub(r"\D", "", str(raw))
        return ("987" + s.zfill(2)) if s and len(s) <= 2 else s


def build_nc():
    rawc = get_geojson(NC_SERVICE + "/0")
    rawp = get_geojson(NC_SERVICE + "/1")

    communes = []
    for f in rawc.get("features", []):
        p = f.get("properties") or {}
        name = first(p, "nom", "NOM")
        code = first(p, "code_com", "CODE_COM", "code")
        if not name or not code or not f.get("geometry"):
            continue
        code = str(code).strip()
        if code.isdigit() and len(code) <= 2:
            code = "988" + code.zfill(2)
        communes.append(feature(code, name, shape(f["geometry"]), region="988", territory="NC"))

    provinces = []
    for i, f in enumerate(rawp.get("features", []), 1):
        p = f.get("properties") or {}
        name = first(p, "nom", "NOM", "province", "nom_prov") or f"Province {i}"
        raw = first(p, "code_prov", "CODE_PROV", "code", "id") or i
        provinces.append(feature("988-P" + str(raw), name, shape(f["geometry"]), region="988", territory="NC"))

    by = feature_name_map(communes)
    groups, group_centres, missing = [], {}, {}
    for code, name, members, centre in NC_GROUPS:
        selected, absent = [], []
        for m in members:
            x = find_by_name(communes, m)
            selected.append(x) if x else absent.append(m)
        if absent:
            missing[name] = absent
        u = union_features(selected, code, name, region="988", dept="988", territory="NC", kind="syndicat_intercommunal")
        if u:
            groups.append(u)
            group_centres[code] = {"name": centre, "at": POINTS.get(centre)}

    region = union_features(provinces or communes, "988", "Nouvelle-Calédonie", region="988", territory="NC")
    province_codes = {fold(f["properties"]["nom"]): f["properties"]["code"] for f in provinces}

    def pcode(fragment):
        for k, v in province_codes.items():
            if fold(fragment) in k:
                return v
        return ""

    centres = [
        {"name": "Nouméa", "at": POINTS["Nouméa"], "rank": "region", "level": 3, "code": "988", "territory": "nc"},
        {"name": "Nouméa", "at": POINTS["Nouméa"], "rank": "department", "level": 2, "code": pcode("sud"), "territory": "nc"},
        {"name": "Koné", "at": POINTS["Koné"], "rank": "department", "level": 2, "code": pcode("nord"), "territory": "nc"},
        {"name": "Wé", "at": POINTS["Wé"], "rank": "department", "level": 2, "code": pcode("iles"), "territory": "nc"},
        {"name": "La Foa", "at": POINTS["La Foa"], "rank": "subpref", "level": 2, "code": pcode("sud"), "territory": "nc", "note": "siège de la subdivision administrative Sud"},
        {"name": "Poindimié", "at": POINTS["Poindimié"], "rank": "subpref", "level": 2, "code": pcode("nord"), "territory": "nc", "note": "antenne de la subdivision administrative Nord"},
    ]

    base = OUT / "nc"
    write_json(base / "communes.geojson", fc(communes))
    write_json(base / "departements.geojson", fc(provinces))
    write_json(base / "groupements.geojson", fc(groups))
    write_json(base / "regions.geojson", fc([region]))
    write_json(base / "commune-centers.json", {f["properties"]["code"]: representative_latlng(f) for f in communes})
    write_json(base / "centers.json", centres)
    write_json(base / "group-centers.json", group_centres)
    return {"communes": communes, "departements": provinces, "groupements": groups, "regions": [region], "centers": centres, "group_centers": group_centres, "missing": missing}


def build_pf():
    raw = get_geojson(PF_LAYER)
    allf = raw.get("features", [])

    raw_subs = []
    normal_communes, island_communes = [], []
    for f in allf:
        p = f.get("properties") or {}
        nature = fold(first(p, "nature_administrative"))
        if not f.get("geometry"):
            continue
        if nature == "subdivision":
            name = first(p, "subdi_nom", "nom", "label")
            sid = first(p, "subdi_id", "id", "OBJECTID")
            if name:
                raw_subs.append(feature(f"987-S{sid}", name, shape(f["geometry"]), region="987", territory="PF"))
        elif nature in {"commune", "commniles", "commune300m"}:
            name = first(p, "com_nom", "nom", "label")
            code = pf_commune_code(p)
            if not name or not code:
                continue
            target = island_communes if nature in {"commniles", "commune300m"} else normal_communes
            target.append(feature(code, name, shape(f["geometry"]), region="987", territory="PF"))

    normal_communes = merge_same(normal_communes, "987")
    island_communes = merge_same(island_communes, "987")
    normal_by = {f["properties"]["code"]: f for f in normal_communes}
    island_by = {f["properties"]["code"]: f for f in island_communes}

    # Prefer the real land/island geometry. Fall back to the administrative
    # commune polygon only where Tefenua does not provide a land representation.
    communes = []
    for code in sorted(set(normal_by) | set(island_by)):
        src = island_by.get(code) or normal_by.get(code)
        g = shape(src["geometry"])
        sub = assign_subdivision(g, raw_subs)
        props = src["properties"]
        extra = {"region": "987", "territory": "PF"}
        if sub:
            extra["subdivision_code"] = sub["properties"]["code"]
            extra["subdivision_name"] = sub["properties"]["nom"]
        communes.append(feature(code, props["nom"], g, **extra))

    # Subdivisions are rendered as the union of their islands, not huge marine
    # administrative polygons. This is what makes the archipelagos readable.
    subdivisions = []
    sub_groups = {}
    for f in communes:
        sid = f["properties"].get("subdivision_code")
        if sid:
            sub_groups.setdefault(sid, []).append(f)
    raw_sub_by_code = {f["properties"]["code"]: f for f in raw_subs}
    for sid, members in sub_groups.items():
        name = members[0]["properties"].get("subdivision_name") or raw_sub_by_code.get(sid, {}).get("properties", {}).get("nom") or sid
        u = union_features(members, sid, name, region="987", territory="PF")
        if u:
            subdivisions.append(u)

    groups, group_centres, missing = [], {}, {}
    for code, name, members, centre in PF_GROUPS:
        selected, absent = [], []
        for m in members:
            x = find_by_name(communes, m)
            selected.append(x) if x else absent.append(m)
        if absent:
            missing[name] = absent
        u = union_features(selected, code, name, region="987", dept="987", territory="PF", kind="communaute_de_communes")
        if u:
            groups.append(u)
            group_centres[code] = centre

    region = union_features(communes, "987", "Polynésie française", region="987", territory="PF")
    sub_codes = {fold(f["properties"]["nom"]): f["properties"]["code"] for f in subdivisions}

    def scode(fragment):
        frag = fold(fragment)
        for k, v in sub_codes.items():
            if frag in k:
                return v
        return ""

    centres = [
        {"name": "Papeete", "at": POINTS["Papeete"], "rank": "region", "level": 3, "code": "987", "territory": "pf"},
        {"name": "Papeete", "at": POINTS["Papeete"], "rank": "department", "level": 2, "code": scode("ilesduvent"), "territory": "pf"},
        {"name": "Uturoa", "at": POINTS["Uturoa"], "rank": "department", "level": 2, "code": scode("ilessouslevent"), "territory": "pf"},
        {"name": "Taiohae", "at": POINTS["Taiohae"], "rank": "department", "level": 2, "code": scode("marquises"), "territory": "pf"},
        {"name": "Tubuai", "at": POINTS["Tubuai"], "rank": "department", "level": 2, "code": scode("australes"), "territory": "pf", "note": "centre administratif de l'archipel"},
        {"name": "Papeete", "at": POINTS["Papeete"], "rank": "department", "level": 2, "code": scode("tuamotugambier"), "territory": "pf", "note": "siège de la subdivision Tuamotu-Gambier"},
    ]

    base = OUT / "pf"
    write_json(base / "communes.geojson", fc(communes))
    write_json(base / "departements.geojson", fc(subdivisions))
    write_json(base / "groupements.geojson", fc(groups))
    write_json(base / "regions.geojson", fc([region]))
    write_json(base / "commune-centers.json", {f["properties"]["code"]: representative_latlng(f) for f in communes})
    write_json(base / "centers.json", centres)
    write_json(base / "group-centers.json", group_centres)
    return {"communes": communes, "departements": subdivisions, "groupements": groups, "regions": [region], "centers": centres, "group_centers": group_centres, "missing": missing}


def slot_centers():
    # Prefer the actual CARTO PLUS locations of Saint-Barthélemy / Saint-Martin.
    defaults = {"pf": (15.0, -8.0), "nc": (15.0, -5.8)}
    if not IGN_COLLECTIVITIES.exists():
        return defaults
    try:
        data = json.loads(IGN_COLLECTIVITIES.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    found = {}
    for f in data.get("features", []):
        p = f.get("properties") or {}
        code = str(p.get("code") or "")
        name = fold(p.get("nom") or "")
        kind = "pf" if code == "977" or "saintbarthelemy" in name else "nc" if code == "978" or name == "saintmartin" else None
        if not kind:
            continue
        g = shape(f["geometry"])
        rp = g.representative_point()
        found[kind] = (float(rp.y), float(rp.x))
    return {**defaults, **found}


def uniform_transformer(bounds, target_center, target_w, target_h):
    minx, miny, maxx, maxy = bounds
    w, h = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    scale = min(target_w / w, target_h / h)
    sx, sy = (minx + maxx) / 2, (miny + maxy) / 2
    ty, tx = target_center

    def transform_geom(g):
        x = affinity.translate(g, xoff=-sx, yoff=-sy)
        x = affinity.scale(x, xfact=scale, yfact=scale, origin=(0, 0))
        return affinity.translate(x, xoff=tx, yoff=ty)

    def transform_point(at):
        lat, lon = at
        p = transform_geom(Point(lon, lat))
        return [float(p.y), float(p.x)]

    return transform_geom, transform_point


PF_LAYOUT = {
    "ilesduvent": (-0.34, 0.04, 0.36, 0.34),
    "ilessouslevent": (-0.78, 0.13, 0.31, 0.27),
    "marquises": (0.53, 0.61, 0.31, 0.38),
    "australes": (-0.58, -0.60, 0.34, 0.28),
    "tuamotugambier": (0.35, -0.10, 0.72, 0.61),
}


def pf_sub_key(name):
    n = fold(name)
    if "souslevent" in n:
        return "ilessouslevent"
    if "ilesduvent" in n or n.endswith("duvent"):
        return "ilesduvent"
    if "marquises" in n:
        return "marquises"
    if "australes" in n:
        return "australes"
    if "tuamotu" in n or "gambier" in n:
        return "tuamotugambier"
    return ""


def build_pf_overview(pf, center):
    # A cartogram inspired by the familiar PF archipelago map: each archipelago
    # keeps its internal island pattern, but ocean distances are compressed.
    ty, tx = center
    sub_members = {}
    for f in pf["communes"]:
        key = pf_sub_key(f["properties"].get("subdivision_name", ""))
        if key:
            sub_members.setdefault(key, []).append(f)

    transforms = {}
    for key, members in sub_members.items():
        g = unary_union([shape(f["geometry"]) for f in members])
        dx, dy, wf, hf = PF_LAYOUT.get(key, (0, 0, .4, .4))
        # The full PF slot is about 2.15° x 1.65°.
        local_center = (ty + dy * 1.55, tx + dx * 2.05)
        transforms[key] = uniform_transformer(g.bounds, local_center, max(.18, wf * 2.05), max(.16, hf * 1.55))

    def t_commune(f):
        key = pf_sub_key(f["properties"].get("subdivision_name", ""))
        tr = transforms.get(key)
        if not tr:
            return None
        g = tr[0](shape(f["geometry"]))
        # Tiny atolls disappear at national scale. Add a very small visual
        # minimum while preserving their actual island position.
        min_width = 0.045
        minx, miny, maxx, maxy = g.bounds
        if max(maxx - minx, maxy - miny) < min_width:
            g = g.buffer(min_width / 2)
        return feature(f["properties"]["code"], f["properties"]["nom"], g, **{k:v for k,v in f["properties"].items() if k not in {"code","nom"}})

    communes = [x for f in pf["communes"] if (x := t_commune(f))]

    def unions_from_codes(source):
        out = []
        c_by = {f["properties"]["code"]: f for f in communes}
        for f in source:
            code = f["properties"]["code"]
            if code == "987":
                members = list(c_by.values())
            elif code.startswith("987-S"):
                members = [x for x in communes if x["properties"].get("subdivision_code") == code]
            else:
                # Recover membership from intersection in true geography.
                trueg = shape(f["geometry"])
                members = []
                for orig in pf["communes"]:
                    if trueg.intersects(shape(orig["geometry"]).representative_point()):
                        mapped = c_by.get(orig["properties"]["code"])
                        if mapped:
                            members.append(mapped)
            u = union_features(members, code, f["properties"]["nom"], **{k:v for k,v in f["properties"].items() if k not in {"code","nom"}})
            if u:
                out.append(u)
        return out

    deps = unions_from_codes(pf["departements"])
    groups = unions_from_codes(pf["groupements"])
    region = unions_from_codes(pf["regions"])

    overview_centers = []
    for x in pf["centers"]:
        # Choose an archipelago from the department code when possible, else
        # use the city/locality itself.
        code = x.get("code", "")
        city = fold(x["name"])
        # Physical locality wins over the administrative unit: the
        # Tuamotu-Gambier subdivision office is in Papeete, so its marker must
        # stay with Tahiti rather than be projected into the Tuamotu cluster.
        key = ""
        if city in {fold("Papeete"), fold("Taravao")}:
            key = "ilesduvent"
        elif city == fold("Uturoa"):
            key = "ilessouslevent"
        elif city == fold("Taiohae"):
            key = "marquises"
        elif city == fold("Tubuai"):
            key = "australes"
        elif city in {fold("Rangiroa"), fold("Hao")}:
            key = "tuamotugambier"
        if not key:
            dep = next((d for d in pf["departements"] if d["properties"]["code"] == code), None)
            key = pf_sub_key(dep["properties"]["nom"]) if dep else ""
        tr = transforms.get(key)
        if tr:
            overview_centers.append({**x, "overview_at": tr[1](x["at"])})
    return {"communes": communes, "departements": deps, "groupements": groups, "regions": region, "centers": overview_centers}


def build_nc_overview(nc, center):
    whole = shape(nc["regions"][0]["geometry"])
    tr, tp = uniform_transformer(whole.bounds, center, 1.55, 1.65)

    def transform_fc(items):
        out = []
        for f in items:
            out.append(feature(f["properties"]["code"], f["properties"]["nom"], tr(shape(f["geometry"])), **{k:v for k,v in f["properties"].items() if k not in {"code","nom"}}))
        return out

    return {
        "communes": transform_fc(nc["communes"]),
        "departements": transform_fc(nc["departements"]),
        "groupements": transform_fc(nc["groupements"]),
        "regions": transform_fc(nc["regions"]),
        "centers": [{**x, "overview_at": tp(x["at"])} for x in nc["centers"]],
    }


def write_overview(kind, data):
    base = OUT / kind / "overview"
    for level in ("communes", "departements", "groupements", "regions"):
        write_json(base / f"{level}.geojson", fc(data[level]))
    write_json(base / "centers.json", data["centers"])
    write_json(base / "commune-centers.json", {f["properties"]["code"]: representative_latlng(f) for f in data["communes"]})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    nc = build_nc()
    pf = build_pf()
    slots = slot_centers()
    write_overview("nc", build_nc_overview(nc, slots["nc"]))
    write_overview("pf", build_pf_overview(pf, slots["pf"]))

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"nc": NC_SERVICE, "pf": PF_LAYER},
        "nc": {
            "communes": len(nc["communes"]),
            "departements": len(nc["departements"]),
            "groupements": len(nc["groupements"]),
            "regions": 1,
            "missing_group_members": nc["missing"],
        },
        "pf": {
            "communes": len(pf["communes"]),
            "departements": len(pf["departements"]),
            "groupements": len(pf["groupements"]),
            "regions": 1,
            "missing_group_members": pf["missing"],
            "display_geometry": "land/island polygons from COMM_NILES/COMMUNE300M where available",
        },
        "overview_slots": slots,
        "notes": {
            "nc_departements": "3 provinces",
            "nc_groupements": "5 groupements territoriaux principaux affichés (SIGN, SIVM Sud, SIVOM VKP, SIVM Nord, SIVM Côte Est). Le SIVU Tipeep, qui recouvre Touho/Poindimié et chevauche le SIVM Côte Est, n'est pas utilisé comme couche principale afin d'éviter une fausse partition superposée.",
            "pf_departements": "5 subdivisions administratives, rendered as unions of island land polygons.",
            "pf_groupements": "7 communities of communes, rendered as unions of member islands.",
            "pf_overview": "archipelago cartogram preserving each archipelago's internal island pattern while compressing ocean distances.",
        },
    }
    write_json(OUT / "manifest.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
