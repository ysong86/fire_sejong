# -*- coding: utf-8 -*-
"""세종시 전역 건물 외곽선·속성 → data/raw/bldg_tiles/*.json

  python tools/fetch_buildings.py

- 브이월드 WFS lt_c_bldginfo(GIS건물통합정보) — 구조(strct_cd)·용도(usability)·사용승인일·층수·연면적이 붙어 온다.
- 키는 생활권 상황판 config.json 의 vworld_key. 키 등록 주소(ysong86.github.io)를 domain·Referer 로 보내야 한다.
- 상가공실 3D 작업(sejong_vacant/tools/fetch_buildings.py)과 같은 방식, 범위만 행복도시 → 세종시 전역(외곽선).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
TILES = os.path.join(HERE, "data", "raw", "bldg_tiles")
STEP = 0.006
PAGE = 1000
REF = "https://ysong86.github.io/"


def key():
    with open(os.path.join(ROOT, "sejong_livingzone", "config.json"), encoding="utf-8") as f:
        return json.load(f)["vworld_key"]


def outline():
    d = json.load(open(os.path.join(ROOT, "sejong_traffic", "assets", "sejong_admin.json"), encoding="utf-8"))
    return d["outline"]


def inside(x, y, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def in_city(x, y, rings):
    return any(inside(x, y, r) for r in rings)


def wfs(k, bbox, start):
    q = dict(service="WFS", version="1.1.0", request="GetFeature", typename="lt_c_bldginfo",
             bbox=f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]},EPSG:4326", srsname="EPSG:4326",
             output="application/json", maxfeatures=str(PAGE), startindex=str(start), key=k, domain=REF)
    url = "https://api.vworld.kr/req/wfs?" + urllib.parse.urlencode(q)
    for a in range(4):
        try:
            t = urllib.request.urlopen(urllib.request.Request(url, headers={"Referer": REF, "User-Agent": "Mozilla/5.0"}), timeout=90).read()
            if t[:1] == b"{":
                return json.loads(t)["features"]
        except Exception:
            pass
        time.sleep(1.5 + a)
    raise RuntimeError("WFS 실패 " + str(bbox))


def grab(k, bb, depth=0):
    """한 타일 전부. 조치원 시가지처럼 무거운 타일은 실패하면 4등분해서 다시 받는다."""
    try:
        feats, s = [], 0
        while True:
            f = wfs(k, bb, s)
            feats += f
            if len(f) < PAGE:
                return feats
            s += PAGE
    except RuntimeError:
        if depth >= 3:
            raise
        mx, my = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        out = []
        for q in ((bb[0], bb[1], mx, my), (mx, bb[1], bb[2], my), (bb[0], my, mx, bb[3]), (mx, my, bb[2], bb[3])):
            out += grab(k, q, depth + 1)
        return out


def main():
    k = key()
    rings = outline()
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    os.makedirs(TILES, exist_ok=True)
    x0, y0 = min(xs), min(ys)
    nx, ny = int((max(xs) - x0) / STEP) + 1, int((max(ys) - y0) / STEP) + 1
    n = 0
    for i in range(nx):
        for j in range(ny):
            p = os.path.join(TILES, f"{i}_{j}.json")
            if os.path.exists(p):
                continue
            bb = (x0 + i * STEP, y0 + j * STEP, x0 + (i + 1) * STEP, y0 + (j + 1) * STEP)
            pts = [(bb[0] + a * STEP / 4, bb[1] + b * STEP / 4) for a in range(5) for b in range(5)]
            if not any(in_city(x, y, rings) for x, y in pts) and not any(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in zip(xs, ys)):
                json.dump([], open(p, "w"))
                continue
            feats = grab(k, bb)
            json.dump(feats, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            n += 1
            print(f"{i}_{j}", len(feats), flush=True)
    print("done tiles", n)


if __name__ == "__main__":
    main()
