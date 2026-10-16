# -*- coding: utf-8 -*-
"""119안전센터(소방청 현황 2026-07-01) 주소 → 좌표(브이월드 getcoord) + OSM 119지역대 → data/stations.json"""
import json, os, urllib.parse, urllib.request
import pandas as pd
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
k = json.load(open(os.path.join(ROOT, "sejong_livingzone", "config.json"), encoding="utf-8"))["vworld_key"]

def geo(addr):
    for t in ("road", "parcel"):
        q = dict(service="address", request="getcoord", version="2.0", crs="epsg:4326", address=addr, refine="true",
                 simple="false", format="json", type=t, key=k)
        d = json.loads(urllib.request.urlopen("https://api.vworld.kr/req/address?" + urllib.parse.urlencode(q), timeout=30).read())
        if d["response"]["status"] == "OK":
            p = d["response"]["result"]["point"]
            return float(p["x"]), float(p["y"])
    return None

d = pd.read_csv(os.path.join(HERE, "data", "raw", "centers", "소방청 119안전센터 주소 및 전화번호(20260701).csv"), encoding="cp949")
d = d[d["시도본부"].astype(str).str.contains("세종")]
out = []
for _, r in d.iterrows():
    xy = geo(r["주소"])
    out.append({"name": r["119안전센터명"], "org": r["소방서명"], "kind": "center", "addr": r["주소"], "lon": xy[0], "lat": xy[1]})
    print(out[-1])
osm = json.load(open(os.path.join(HERE, "data", "raw", "osm_fire.json"), encoding="utf-8"))["elements"]
for e in osm:
    nm = e["tags"].get("name") or ""
    if "지역대" in nm and "의용" not in nm:
        lat = e.get("lat") or e["center"]["lat"]; lon = e.get("lon") or e["center"]["lon"]
        out.append({"name": nm.replace("조치원소방서 ", ""), "org": "", "kind": "post", "addr": "OSM", "lon": lon, "lat": lat})
        print(out[-1])
json.dump({"source": "소방청 119안전센터 주소(2026-07-01) + OpenStreetMap 119지역대", "stations": out},
          open(os.path.join(HERE, "data", "stations.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
