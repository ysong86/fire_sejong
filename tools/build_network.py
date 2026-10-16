# -*- coding: utf-8 -*-
"""전국 표준노드링크(MOCT_LINK) → 세종 주변만 잘라 data/network.json

  python tools/build_network.py

- 원본: 국가교통정보센터 [2026-10-14]NODELINKDATA.zip (data/raw/nodelink). 좌표계 ITRF2000 중부원점(lon0 127, lat0 38,
  FE 200000, FN 600000, k=1, GRS80) — pyproj 가 없어 TM 역변환을 직접 한다(오차 mm 수준).
- 링크는 방향이 있다(F_NODE→T_NODE). ITS 소통정보의 linkId 와 같은 체계라 속도를 그대로 붙일 수 있다.
- 범위: 세종 외곽선 경계상자 + 3km. 시 경계 밖 도로도 경로로는 쓰인다(세종 안 두 지점 사이 지름길).
"""
from __future__ import annotations

import json
import math
import os
import zipfile

import shapefile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(HERE, "data", "raw", "nodelink")

A = 6378137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)
K0, LON0, LAT0, FE, FN = 1.0, math.radians(127.0), math.radians(38.0), 200000.0, 600000.0


def _m(phi):
    e4, e6 = E2 * E2, E2 ** 3
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


M0 = _m(LAT0)


def tm_to_ll(x, y):
    m = M0 + (y - FN) / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = EP2 * math.cos(p1) ** 2
    t1 = math.tan(p1) ** 2
    n1 = A / math.sqrt(1 - E2 * math.sin(p1) ** 2)
    r1 = A * (1 - E2) / (1 - E2 * math.sin(p1) ** 2) ** 1.5
    d = (x - FE) / (n1 * K0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lon), math.degrees(lat)


def main():
    if not os.path.exists(os.path.join(RAW, "MOCT_LINK.shp")):
        z = zipfile.ZipFile(os.path.join(RAW, "NODELINKDATA.zip"))
        for n in ("MOCT_LINK.dbf", "MOCT_LINK.prj", "MOCT_LINK.shp", "MOCT_LINK.shx"):
            z.extract(n, RAW)
    admin = json.load(open(os.path.join(ROOT, "sejong_traffic", "assets", "sejong_admin.json"), encoding="utf-8"))
    xs = [p[0] for r in admin["outline"] for p in r]
    ys = [p[1] for r in admin["outline"] for p in r]
    pad_x, pad_y = 3000 / 89500, 3000 / 111000
    bb = (min(xs) - pad_x, min(ys) - pad_y, max(xs) + pad_x, max(ys) + pad_y)
    # 경계상자를 TM 으로 대략 옮겨 빠르게 거른다(여유 1km)
    tx0, ty0, tx1, ty1 = 200000, 410000, 250000, 475000   # 세종 ≈ x 210~238km, y 422~461km
    r = shapefile.Reader(os.path.join(RAW, "MOCT_LINK"), encoding="cp949")
    names = [f[0] for f in r.fields[1:]]
    out = []
    for sr in r.iterShapeRecords():
        b = sr.shape.bbox
        if b[2] < tx0 or b[0] > tx1 or b[3] < ty0 or b[1] > ty1:
            continue
        pts = [tm_to_ll(x, y) for x, y in sr.shape.points]
        if not any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in pts):
            continue
        rec = dict(zip(names, sr.record))
        out.append({"id": rec["LINK_ID"], "f": rec["F_NODE"], "t": rec["T_NODE"],
                    "rank": rec["ROAD_RANK"], "name": (rec["ROAD_NAME"] or "").strip(),
                    "lanes": int(rec["LANES"] or 0), "max": int(rec["MAX_SPD"] or 0),
                    "len": round(float(rec["LENGTH"] or 0), 1), "use": rec["ROAD_USE"],
                    "pts": [[round(x, 6), round(y, 6)] for x, y in pts]})
    json.dump({"source": "국가교통정보센터 전국표준노드링크 2026-10-14", "bbox": bb, "links": out},
              open(os.path.join(HERE, "data", "network.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print("links", len(out), Counter(l["rank"] for l in out))


if __name__ == "__main__":
    main()
