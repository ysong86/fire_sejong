# -*- coding: utf-8 -*-
"""세종 화재안전 상황판 — dashboard.html(평문) 생성.

  python analyze.py
  python build.py
  python ../sejong_livingzone/tools/encrypt_page.py dashboard.html site/index.html "세종 화재안전 상황판"   (공개용 암호화)

화면 머리(글꼴·색)는 생활권 상황판 template.html 의 <style> 을 그대로 가져온다 — 다른 상황판과 같은 겉모습.
자료는 열(column) 단위로 묶고 좌표는 정수로 바꿔 크기를 줄인다.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ZONE = os.path.join(ROOT, "sejong_livingzone")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def head():
    t = open(os.path.join(ZONE, "template.html"), encoding="utf-8").read()
    h = t[: t.index("</style>") + len("</style>")]
    h = re.sub(r"<title>.*?</title>", "<title>세종 화재안전 상황판</title>", h)
    h = re.sub(r'<meta name="description"[^>]*>',
               '<meta name="description" content="119안전센터 도달시간(ITS 실측 속도)과 건물 화재위험 추정으로 본 세종시 화재 대응 취약지">', h)
    return h


def pack(a):
    x0, y0 = a["origin"]
    cols = a["bcols"]
    B = a["b"]
    col = {c: [r[i] for r in B] for i, c in enumerate(cols)}
    col["x"] = [round((v - x0) * 1e5) for v in col["x"]]
    col["y"] = [round((v - y0) * 1e5) for v in col["y"]]
    col["pp"] = [round(v * 10) for v in col["pp"]]
    nodes = a["nodes"]
    E = a["edges"]
    ns = len(a["net"]["slots"])
    out = {k: v for k, v in a.items() if k not in ("b", "nodes", "edges", "ncell", "narrow")}
    out["B"] = col
    out["NX"] = [round((p[0] - x0) * 1e5) for p in nodes]
    out["NY"] = [round((p[1] - y0) * 1e5) for p in nodes]
    out["NC"] = [-1 if c is None else c[0] * 10000 + c[1] for c in a["ncell"]]
    out["EF"] = [e[0] for e in E]
    out["ET"] = [e[1] for e in E]
    out["EW"] = [[e[2 + s] for e in E] for s in range(ns)]
    out["narrow"] = [[[round((p[0] - x0) * 1e5), round((p[1] - y0) * 1e5)] for p in l] for l in a["narrow"]]
    admin = load(os.path.join(ROOT, "sejong_livingzone", "assets", "sejong_units.json"))
    admin["dongs"] = admin["units"]
    out["outline"] = [[[round(p[0], 5), round(p[1], 5)] for p in r] for r in admin["outline"]]
    out["dpoly"] = [[[[round(p[0], 5), round(p[1], 5)] for p in r] for r in d["rings"]] for d in admin["dongs"]]
    cfg = load(os.path.join(ROOT, "sejong_traffic", "config.json"))
    out["vworld"] = (cfg.get("site", {}).get("basemap") or {}).get("key") or ""
    return out


def main():
    a = load(os.path.join(HERE, "data", "analysis.json"))
    d = pack(a)
    body = open(os.path.join(HERE, "body.html"), encoding="utf-8").read()
    js = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = head() + "\n" + body.replace("/*__DATA__*/null", js)
    open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8").write(html)
    print("dashboard.html", round(len(html.encode("utf-8")) / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
