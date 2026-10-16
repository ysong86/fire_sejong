# -*- coding: utf-8 -*-
"""ITS 소통정보(링크별 속도) 한 장 → data/raw/its/YYYYMMDD_HHMM.json

  python tools/collect_its.py            # 한 번
  python tools/collect_its.py --loop 30  # 30분마다 (Ctrl+C 로 멈춤)

키는 교통안전 상황판 config.json 의 its.key (월 15,000건 운영 계정, 교통 상황판 NAS 수집과 같이 씀).
링크 좌표는 오지 않는다 → 표준노드링크(MOCT_LINK)와 linkId 로 붙인다(tools/build_network.py).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "data", "raw", "its")
BBOX = dict(minX=127.118, maxX=127.421, minY=36.397, maxY=36.743)


def once():
    k = json.load(open(os.path.join(ROOT, "sejong_traffic", "config.json"), encoding="utf-8"))["its"]["key"]
    q = dict(apiKey=k, type="all", drcType="all", getType="json", **BBOX)
    url = "https://openapi.its.go.kr:9443/trafficInfo?" + urllib.parse.urlencode(q)
    for a in range(4):
        try:
            d = json.loads(urllib.request.urlopen(url, timeout=60).read().decode("utf-8"))
            items = d["body"]["items"]
            break
        except Exception as e:
            err = e
            time.sleep(5 + 5 * a)
    else:
        print("실패", err, flush=True)
        return
    rows = {}
    stamp = None
    for it in items:
        try:
            s = float(it["speed"])
        except (TypeError, ValueError):
            continue
        if s <= 0:
            continue   # 속도 0 = 자료 없음(교통 상황판에서 확인)
        rows[it["linkId"]] = round(s, 1)
        stamp = stamp or it.get("createdDate")
    os.makedirs(OUT, exist_ok=True)
    name = (stamp or dt.datetime.now().strftime("%Y%m%d%H%M%S"))[:12]
    name = name[:8] + "_" + name[8:12]
    json.dump({"created": stamp, "speeds": rows}, open(os.path.join(OUT, name + ".json"), "w"), separators=(",", ":"))
    print(name, len(rows), flush=True)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        m = int(sys.argv[sys.argv.index("--loop") + 1])
        while True:
            once()
            time.sleep(m * 60)
    else:
        once()
