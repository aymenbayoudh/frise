#!/usr/bin/env python3
"""Build local administrative layers for New Caledonia and French Polynesia."""
from __future__ import annotations
import json,re,unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

OUT=Path("carto/data/pacific")
NC_SERVICE="https://services1.arcgis.com/TZcrgU6CIbqWt9Qv/arcgis/rest/services/limites_terrestres/FeatureServer"
PF_LAYER="https://services.arcgis.com/L4H4rU26VyhEF588/ArcGIS/rest/services/D%C3%A9coupage_administratif/FeatureServer/0"
TIMEOUT=120
session=requests.Session()
session.headers.update({"User-Agent":"frise-carto-pacific-admin/1.0 (+https://github.com/aymenbayoudh/frise)"})

def get_geojson(url:str,where:str="1=1",out_fields:str="*")->dict[str,Any]:
    params={"where":where,"outFields":out_fields,"returnGeometry":"true","outSR":"4326","f":"geojson"}
    r=session.get(url.rstrip("/")+"/query",params=params,timeout=TIMEOUT);r.raise_for_status()
    data=r.json()
    if data.get("error"): raise RuntimeError(data["error"])
    if data.get("type")!="FeatureCollection": raise RuntimeError(f"Unexpected ArcGIS response from {url}")
    return data

def fold(value:Any)->str:
    s=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+","",s)

def first(props:dict[str,Any],*names:str)->Any:
    lookup={fold(k):v for k,v in props.items()}
    for name in names:
        v=lookup.get(fold(name))
        if v is not None and str(v).strip()!="": return v
    return None

def clean_geometry(geom):
    if not geom:return None
    g=shape(geom)
    if g.is_empty:return None
    if not g.is_valid:g=g.buffer(0)
    return mapping(g)

def write_json(path:Path,obj:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def feature(code,name,geom,**extra):
    return {"type":"Feature","properties":{"code":str(code),"nom":str(name),**{k:v for k,v in extra.items() if v is not None}},"geometry":clean_geometry(geom)}

def fc(features): return {"type":"FeatureCollection","features":[f for f in features if f and f.get("geometry")]}

def union_features(features,code,name,**extra):
    geoms=[shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:return None
    g=unary_union(geoms)
    if g.is_empty:return None
    return feature(code,name,mapping(g),**extra)

def centroid_latlng(f):
    p=shape(f["geometry"]).representative_point()
    return [round(float(p.y),6),round(float(p.x),6)]

NC_GROUPS=[
 ("NC-SIGN","Syndicat intercommunal du Grand Nouméa (SIGN)",["Nouméa","Dumbéa","Mont-Dore","Païta"]),
 ("NC-SIVMSUD","SIVM Sud",["Bourail","Boulouparis","Farino","La Foa","Moindou","Sarraméa","Thio"]),
 ("NC-SIVOMVKP","SIVOM VKP",["Voh","Koné","Pouembout"]),
 ("NC-SIVMNORD","SIVM Nord",["Kaala-Gomen","Koumac","Poum"]),
 ("NC-SIVUTIPEEP","SIVU Tipeep",["Touho","Poindimié"]),
]
PF_GROUPS=[
 ("200027688","Communauté de communes des Îles Marquises (CODIM)",["Fatu Hiva","Hiva Oa","Nuku Hiva","Tahuata","Ua Huka","Ua Pou"]),
 ("200031243","Communauté de communes Hava'i",["Huahine","Maupiti","Tahaa","Taputapuatea","Tumaraa","Uturoa"]),
 ("200094803","Communauté de communes Tereheamanu",["Hitiaa O Te Ra","Papara","Taiarapu Est","Taiarapu Ouest","Teva I Uta"]),
 ("200102358","Communauté de communes Teporionu'u",["Arue","Papeete","Pirae"]),
 ("200102366","Communauté de communes Te Tama a Hiro",["Rapa","Rimatara","Rurutu","Tubuai"]),
 ("934286501","Communauté de communes Mihiroa-Havaiki",["Arutua","Fakarava","Rangiroa"]),
 ("994270916","Communauté de communes Hono Hau",["Gambier","Hao","Hikueru","Reao","Tureia"]),
]

def build_nc():
    rawc=get_geojson(NC_SERVICE+"/0");rawp=get_geojson(NC_SERVICE+"/1")
    communes=[]
    for f in rawc.get("features",[]):
        p=f.get("properties") or {};name=first(p,"nom","NOM");code=first(p,"code_com","CODE_COM","code")
        if not name or not code or not f.get("geometry"):continue
        code=str(code).strip()
        if code.isdigit() and len(code)<=2:code="988"+code.zfill(2)
        communes.append(feature(code,name,f["geometry"],region="988",territory="NC"))
    provinces=[]
    for i,f in enumerate(rawp.get("features",[]),1):
        p=f.get("properties") or {};name=first(p,"nom","NOM","province","nom_prov") or f"Province {i}"
        raw=first(p,"code_prov","CODE_PROV","code","id") or i
        provinces.append(feature("988-P"+str(raw),name,f["geometry"],region="988",territory="NC"))
    by={fold(f["properties"]["nom"]):f for f in communes};groups=[];missing={}
    for code,name,members in NC_GROUPS:
        selected=[];absent=[]
        for m in members:
            x=by.get(fold(m));selected.append(x) if x else absent.append(m)
        if absent:missing[name]=absent
        u=union_features([x for x in selected if x],code,name,region="988",dept="988",territory="NC",kind="syndicat_intercommunal")
        if u:groups.append(u)
    region=union_features(provinces or communes,"988","Nouvelle-Calédonie",region="988",territory="NC")
    base=OUT/"nc";write_json(base/"communes.geojson",fc(communes));write_json(base/"departements.geojson",fc(provinces));write_json(base/"groupements.geojson",fc(groups));write_json(base/"regions.geojson",fc([region]));write_json(base/"commune-centers.json",{f["properties"]["code"]:centroid_latlng(f) for f in communes})
    return {"communes":len(communes),"departements":len(provinces),"groupements":len(groups),"regions":1,"missing_group_members":missing}

def pf_commune_code(props):
    raw=first(props,"com_id","code","id")
    if raw is None:return ""
    try:
        n=int(float(raw));return f"987{n:02d}" if n<100 else str(n)
    except Exception:
        s=re.sub(r"\D","",str(raw));return ("987"+s.zfill(2)) if s and len(s)<=2 else s

def build_pf():
    raw=get_geojson(PF_LAYER);communes=[];commune_fallbacks=[];subs=[]
    for f in raw.get("features",[]):
        p=f.get("properties") or {};nature=fold(first(p,"nature_administrative"))
        if not f.get("geometry"):continue
        if nature=="commune":
            name=first(p,"com_nom","nom","label");code=pf_commune_code(p)
            if name and code:communes.append(feature(code,name,f["geometry"],region="987",territory="PF"))
        elif nature in {"commniles","commune300m"}:
            name=first(p,"com_nom","nom","label");code=pf_commune_code(p)
            if name and code:commune_fallbacks.append(feature(code,name,f["geometry"],region="987",territory="PF"))
        elif nature=="subdivision":
            name=first(p,"subdi_nom","nom","label");sid=first(p,"subdi_id","id","OBJECTID")
            if name:subs.append(feature(f"987-S{sid}",name,f["geometry"],region="987",territory="PF"))
    def merge_same(items):
        groups={}
        for f in items:groups.setdefault(f["properties"]["code"],[]).append(f)
        out=[]
        for code,parts in groups.items():
            u=union_features(parts,code,parts[0]["properties"]["nom"],region="987",territory="PF")
            if u:out.append(u)
        return out
    communes=merge_same(communes);fallbacks=merge_same(commune_fallbacks)
    existing_codes={f["properties"]["code"] for f in communes}
    communes.extend(f for f in fallbacks if f["properties"]["code"] not in existing_codes)
    subs=merge_same(subs)
    by={fold(f["properties"]["nom"]):f for f in communes};groups=[];missing={}
    def commune_member(name):
        key=fold(name)
        if key in by:return by[key]
        # Tefenua can qualify an island/commune name; accept an unambiguous
        # containment match (notably Gambier) after accent/punctuation folding.
        matches=[f for k,f in by.items() if key in k or k in key]
        return matches[0] if len(matches)==1 else None
    for code,name,members in PF_GROUPS:
        selected=[];absent=[]
        for m in members:
            x=commune_member(m);selected.append(x) if x else absent.append(m)
        if absent:missing[name]=absent
        u=union_features([x for x in selected if x],code,name,region="987",dept="987",territory="PF",kind="communaute_de_communes")
        if u:groups.append(u)
    region=union_features(subs or communes,"987","Polynésie française",region="987",territory="PF")
    base=OUT/"pf";write_json(base/"communes.geojson",fc(communes));write_json(base/"departements.geojson",fc(subs));write_json(base/"groupements.geojson",fc(groups));write_json(base/"regions.geojson",fc([region]));write_json(base/"commune-centers.json",{f["properties"]["code"]:centroid_latlng(f) for f in communes})
    return {"communes":len(communes),"departements":len(subs),"groupements":len(groups),"regions":1,"missing_group_members":missing}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"sources":{"nc":NC_SERVICE,"pf":PF_LAYER},"nc":build_nc(),"pf":build_pf(),"notes":{"nc_groupements":"5 syndicats/intercommunalités de gestion des déchets; pas d'EPCI à fiscalité propre.","pf_departements":"Les subdivisions administratives sont utilisées comme niveau analogue au département.","pf_groupements":"Communautés de communes actives identifiées pour 2026."}}
    write_json(OUT/"manifest.json",result);print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
