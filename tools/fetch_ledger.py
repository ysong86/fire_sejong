# -*- coding: utf-8 -*-
"""건축물대장 표제부(세종 전체) → data/raw/ledger.json

  python tools/fetch_ledger.py

- 건축HUB getBrTitleInfo. 키·법정동 목록은 생활권 상황판(config.json portal_key, data/raw/bld_codes.json) 것을 쓴다.
- 생활권 수집본(bld.json)은 구조·층수·지번을 버려서 화재 위험 산정용으로 다시 받는다.
- 지번으로 PNU(19자리)를 만들어 브이월드 건물 외곽선(pnu)과 잇는다.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
ZONE = os.path.join(ROOT, "sejong_livingzone")
URL = ("https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
       "?serviceKey={k}&sigunguCd=36110&bjdongCd={bj}&numOfRows=1000&pageNo={page}&_type=json")
KEEP = ("platGbCd", "bun", "ji", "bjdongCd", "bldNm", "dongNm", "mainAtchGbCd", "mainPurpsCd", "mainPurpsCdNm",
        "etcPurps", "strctCd", "strctCdNm", "etcStrct", "roofCdNm", "grndFlrCnt", "ugrndFlrCnt", "totArea",
        "archArea", "hhldCnt", "fmlyCnt", "hoCnt", "useAprDay", "rideUseElvtCnt", "emgenUseElvtCnt", "heit")


def get(url):
    for a in range(10):
        try:
            t = urllib.request.urlopen(url, timeout=60).read().decode("utf-8")
            return json.loads(t)
        except Exception as e:
            err = e
            time.sleep(2 + 3 * a)
    raise RuntimeError(err)


def main():
    key = json.load(open(os.path.join(ZONE, "config.json"), encoding="utf-8"))["portal_key"]
    codes = sorted(json.load(open(os.path.join(ZONE, "data", "raw", "bld_codes.json"), encoding="utf-8")))
    out = []
    parts = os.path.join(HERE, "data", "raw", "ledger_parts")
    os.makedirs(parts, exist_ok=True)
    for bj in codes:
        pp = os.path.join(parts, bj + ".json")
        if os.path.exists(pp):          # 법정동마다 저장 — 중간에 끊겨도 이어받는다
            out += json.load(open(pp, encoding="utf-8"))
            continue
        mine = []
        page, got = 1, 0
        while True:
            d = get(URL.format(k=urllib.parse.quote(key, safe=""), bj=bj, page=page))
            b = d["response"]["body"]
            it = (b["items"].get("item") or []) if isinstance(b.get("items"), dict) else []
            it = [it] if isinstance(it, dict) else it
            for x in it:
                r = {f: x.get(f) for f in KEEP}
                pg = "2" if str(x.get("platGbCd")) == "1" else "1"     # 대장 0=대지,1=산 → PNU 1=대지,2=산
                r["pnu"] = "36110" + str(x.get("bjdongCd")) + pg + str(x.get("bun") or "0").zfill(4) + str(x.get("ji") or "0").zfill(4)
                mine.append(r)
            got += len(it)
            if not it or got >= int(b.get("totalCount") or 0):     # 한 쪽에 1000을 달라 해도 100건씩 온다
                break
            page += 1
        json.dump(mine, open(pp, "w", encoding="utf-8"), ensure_ascii=False)
        out += mine
        print(bj, len(out), flush=True)
    json.dump({"items": out}, open(os.path.join(HERE, "data", "raw", "ledger.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("done", len(out))


if __name__ == "__main__":
    main()
