# -*- coding: utf-8 -*-
"""세종 화재안전 상황판 — 분석 자료 만들기 → data/analysis.json

  python tools/fetch_buildings.py   (브이월드 건물 외곽선, 처음 한 번)
  python tools/fetch_ledger.py      (건축물대장 표제부, 처음 한 번)
  python tools/build_network.py     (표준노드링크 → 세종 도로망, 처음 한 번)
  python tools/geocode_stations.py  (119안전센터 좌표)
  python tools/collect_its.py --loop 30   (ITS 속도 표본을 시간대별로 모은다)
  python analyze.py
  python build.py

도달시간은 화면(브라우저)이 다시 계산한다 — 시간대 전환·가상 지역대 시험을 바로 보여주려고.
여기서는 그 재료(시간대별 링크 통행시간, 건물→도로 접속)와 건물별 위험 요소 점수를 만든다.
"""
from __future__ import annotations

import datetime as dt
import glob
import heapq
import json
import math
import os
import statistics
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
RAW = os.path.join(DATA, "raw")

KX, KY = 89_500.0, 111_000.0          # 위도 36.5° 근방 1도당 m
CELL = 250                             # 격자 한 변(m)
ACCESS_KMH = 20.0                      # 도로에서 건물까지 마지막 구간(골목·단지 안) 속도 가정
DETOUR = 1.3                           # 직선거리 → 실제 진입 거리 보정
OUTLIER_LEN, OUTLIER_RATIO = 200, 0.25   # 200m 넘는 링크인데 제한속도 25% 미만 = 관측 이상치(강변길 470m 시속 8km 등)
MIN_LIMIT = 30                         # 제한속도 10~20km/h 로 등록된 단지·둔치 도로도 30 으로 본다(소방차 기준)
JOIN_M = 30.0                          # 이 거리 안 노드는 같은 교차로로 보고 잇는다
JOIN_KMH = 15.0
MIN_FOOT = 20.0                        # ㎡, 이보다 작은 외곽선(창고 부속·화장실 등)은 뺀다
DEFAULT_KMH = {"101": 90, "102": 70, "103": 60, "104": 50, "105": 50, "106": 50, "107": 30}
SLOTS = [("night", "심야(23~05시)", range(23, 30)), ("am", "출근(07~09시)", range(7, 10)),
         ("pm", "퇴근(17~19시)", range(17, 20)), ("day", "평시(그 밖)", None)]

USE = {  # 용도 앞 두 자리 → (이름, 점수) — 인명 피해(주거·노유자·의료·숙박)와 화재하중(공장·창고·위험물)을 함께 본다
    "01": ("단독주택", 70), "02": ("공동주택", 55), "03": ("제1종 근린생활", 50), "04": ("제2종 근린생활", 60),
    "05": ("문화·집회", 55), "06": ("종교", 45), "07": ("판매", 65), "08": ("운수", 40), "09": ("의료", 85),
    "10": ("교육연구", 50), "11": ("노유자", 95), "12": ("수련", 60), "13": ("운동", 35), "14": ("업무", 35),
    "15": ("숙박", 80), "16": ("위락", 75), "17": ("공장", 80), "18": ("창고", 75), "19": ("위험물 저장·처리", 100),
    "20": ("자동차 관련", 60), "21": ("동식물 관련(축사 등)", 65), "22": ("자원순환", 60), "23": ("교정·군사", 40),
    "24": ("방송통신", 40), "25": ("발전", 60), "26": ("묘지 관련", 30), "27": ("관광휴게", 45), "28": ("장례", 45),
    "29": ("야영장", 60),
}
STRUCT = {"wood": ("목구조", 100), "panel": ("경량철골·조립식", 90), "masonry": ("조적(벽돌·블록)", 60),
          "steel": ("일반철골", 50), "concrete": ("콘크리트", 15), "unk": ("미상", 50)}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


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


class Dongs:
    def __init__(self):
        # 행정동 25곳(생활권 상황판이 OSM 외곽링 문제를 바로잡은 경계) — 주민등록 인구가 행정동 단위라 이름이 맞는다
        a = load(os.path.join(ROOT, "sejong_livingzone", "assets", "sejong_units.json"))
        a["dongs"] = a["units"]
        self.outline = a["outline"]
        self.d = [(x["name"], x["kind"], x["rings"],
                   (min(p[0] for r in x["rings"] for p in r), min(p[1] for r in x["rings"] for p in r),
                    max(p[0] for r in x["rings"] for p in r), max(p[1] for r in x["rings"] for p in r)))
                  for x in a["dongs"]]
        self.names = [x[0] for x in self.d]

    def of(self, x, y):
        for i, (_, _, rings, bb) in enumerate(self.d):
            if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and any(inside(x, y, r) for r in rings):
                return i
        return -1


def struct_from_name(nm, etc=""):
    s = (nm or "") + " " + (etc or "")
    if not s.strip():
        return "unk"
    if "목" in s and "철골" not in s:
        return "wood"
    if any(w in s for w in ("경량철골", "강파이프", "조립", "샌드위치", "판넬", "패널", "컨테이너")):
        return "panel"
    if any(w in s for w in ("철근콘크리트", "철골철근", "철골콘크리트", "프리캐스트", "콘크리트")):
        return "concrete"
    if "철골" in s:
        return "steel"
    if "강구조" in s:
        return "steel"
    if any(w in s for w in ("벽돌", "블록", "블럭", "조적", "석조", "석구조", "흙")):
        return "masonry"
    return "unk"


def struct_from_code(c):
    c = str(c or "")
    if not c:
        return "unk"
    if c[0] == "1":
        return "masonry"
    if c[0] in "24":
        return "concrete"
    if c == "31":
        return "steel"
    if c[0] == "3":
        return "panel"
    if c[0] == "5":
        return "wood"
    if c in ("61", "62", "72"):       # 시멘트블럭·흙벽돌 (대장 구조명과 대조해 확인)
        return "masonry"
    if c == "63":                     # 조립식판넬
        return "panel"
    return "unk"


def yr(v):
    v = str(v or "").strip()[:4]
    return int(v) if v.isdigit() else 0


def num(v):
    try:
        return float(str(v).strip() or 0)
    except ValueError:
        return 0.0


def age_score(y):
    if not y:
        return 60
    return 100 if y < 1980 else 85 if y < 1990 else 65 if y < 2000 else 40 if y < 2012 else 15


def scale_score(fl, area):
    f = 100 if fl >= 16 else 75 if fl >= 11 else 45 if fl >= 6 else 15
    a = 80 if area >= 10000 else 55 if area >= 3000 else 35 if area >= 1000 else 15
    return max(f, a)


# ── 인구·고령 ──────────────────────────────────────────────
def dong_people(names):
    m = load(os.path.join(ROOT, "sejong_livingzone", "data", "raw", "mois_age.json"))
    pop, old = defaultdict(int), defaultdict(int)
    for it in m["items"]:
        if it.get("tong") or it.get("ban"):
            continue
        n = it["dongNm"]
        n = "도담·어진동" if n in ("도담동", "어진동") else n     # 생활권 상황판 경계에서 둘을 합쳐 둠
        pop[n] += int(it["totNmprCnt"])
        old[n] += sum(int(it.get(f"{s}{a}AgeNmprCnt") or 0) for s in ("male", "feml") for a in (70, 80, 90, 100))
    out = {}
    for n in names:
        p = pop.get(n, 0)
        out[n] = {"pop": p, "old70": old.get(n, 0), "share": round(old[n] / p * 100, 1) if p else None}
    return out, m.get("ym")


# ── 건물 ───────────────────────────────────────────────────
def buildings(dongs, dp):
    led = load(os.path.join(RAW, "ledger.json"))["items"]
    by_pnu = defaultdict(list)
    for r in led:
        if str(r.get("mainAtchGbCd")) == "0":
            by_pnu[r["pnu"]].append(r)
    seen, out = set(), []
    stat = Counter()
    rng = {}
    sh = [v["share"] for v in dp.values() if v["share"] is not None]
    lo, hi = min(sh), max(sh)
    for fn in glob.glob(os.path.join(RAW, "bldg_tiles", "*.json")):
        for f in load(fn):
            uid = f.get("id")
            if uid in seen:
                continue
            seen.add(uid)
            p = f["properties"]
            g = f["geometry"]
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            ring = polys[0][0]
            # 넓이(신발끈)·중심
            ax = sum((ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]) for i in range(len(ring) - 1)) / 2
            foot = abs(ax) * KX * KY
            if foot < MIN_FOOT:
                stat["tiny"] += 1
                continue
            cx = sum(q[0] for q in ring[:-1]) / max(1, len(ring) - 1)
            cy = sum(q[1] for q in ring[:-1]) / max(1, len(ring) - 1)
            di = dongs.of(cx, cy)
            if di < 0:
                stat["outside"] += 1
                continue
            use = (p.get("usability") or "")[:2]
            year = yr(p.get("useapr_day"))
            st = struct_from_code(p.get("strct_cd"))
            fl = int(p.get("grnd_flr") or 0)
            area = float(p.get("totalarea") or 0)
            hh = 0
            src = "v" if use else ""
            cands = by_pnu.get(p.get("pnu") or "", [])
            if cands:
                r = None
                if len(cands) == 1:
                    r = cands[0]
                else:
                    dn = (p.get("dong_nm") or "").replace(" ", "")
                    m = [c for c in cands if dn and (c.get("dongNm") or "").replace(" ", "") == dn]
                    r = m[0] if m else max(cands, key=lambda c: num(c.get("totArea")))
                    if not m:
                        area = 0   # 여러 동이 한 필지 — 연면적은 외곽선×층수로 대신
                use = use or (r.get("mainPurpsCd") or "")[:2]
                year = year or yr(r.get("useAprDay"))
                s2 = struct_from_name(r.get("strctCdNm"), r.get("etcStrct"))
                st = st if st != "unk" else s2
                fl = fl or int(num(r.get("grndFlrCnt")))
                if len(cands) == 1:
                    area = area or num(r.get("totArea"))
                    hh = int(num(r.get("hhldCnt")) + num(r.get("fmlyCnt")))
                src = src or "l"
            if year and (year < 1900 or year > 2026):
                year = 0
            if not area:
                area = foot * max(1, fl)
            stat["src_" + (src or "none")] += 1
            ukey = use if use in USE else ""
            resid = ukey in ("01", "02")
            sh_d = dp[dongs.names[di]]["share"]
            vul = 100 if ukey == "11" else (round((sh_d - lo) / (hi - lo) * 100) if (resid and sh_d is not None) else 20)
            out.append({
                "x": cx, "y": cy, "d": di, "u": ukey, "yr": year, "s": st, "fl": fl, "a": round(area), "ft": round(foot),
                "hh": hh, "src": src,
                "c": [USE.get(ukey, ("", 50))[1], age_score(year), STRUCT[st][1], vul, scale_score(fl, area)],
            })
    return out, stat


# ── 도로망 ─────────────────────────────────────────────────
def its_slots(net_ids):
    snaps = defaultdict(list)
    meta = defaultdict(list)
    for fn in sorted(glob.glob(os.path.join(RAW, "its", "*.json"))):
        d = load(fn)
        c = d.get("created") or os.path.basename(fn).replace("_", "")
        t = dt.datetime.strptime(c[:12], "%Y%m%d%H%M")
        h = t.hour if t.hour >= 6 else t.hour + 24
        sk = next((k for k, _, r in SLOTS if r and h in r), "day")
        snaps[sk].append(d["speeds"])
        meta[sk].append(t.strftime("%m-%d") + "(" + "월화수목금토일"[t.weekday()] + ") " + t.strftime("%H:%M"))   # 요일: 주말 표본은 평일 출퇴근을 대표하지 못한다
    out = {}
    for sk, lst in snaps.items():
        sp = {}
        for lid in net_ids:
            v = [s[lid] for s in lst if lid in s]
            if v:
                sp[lid] = statistics.median(v)
        out[sk] = sp
    return out, meta


def network(dongs):
    net = load(os.path.join(DATA, "network.json"))
    links = [l for l in net["links"] if l["len"] > 0]
    ids = {l["id"] for l in links}
    its, meta = its_slots(ids)
    # 표준노드링크(2026판)는 교차로 하나를 진입 방향별 노드(앞 8자리 같고 끝 2자리만 다름)로 쪼개고 회전을 짧은
    # 연결 링크로 잇는다. 연결 링크가 빠진 곳이 많아 앞 8자리로 합친다 → 교차로에서는 어느 방향으로든 회전·유턴 가능.
    node_ix, nodes, acc = {}, [], []
    for l in links:
        for nid, pt in ((l["f"], l["pts"][0]), (l["t"], l["pts"][-1])):
            k = nid[:8]
            if k not in node_ix:
                node_ix[k] = len(nodes)
                nodes.append([0.0, 0.0])
                acc.append(0)
            i = node_ix[k]
            nodes[i][0] += pt[0]
            nodes[i][1] += pt[1]
            acc[i] += 1
    nodes = [[x / c, y / c] for (x, y), c in zip(nodes, acc)]
    for l in links:
        l["f"], l["t"] = l["f"][:8], l["t"][:8]
    n_conn = sum(1 for l in links if l["f"] == l["t"])
    links = [l for l in links if l["f"] != l["t"]]       # 교차로 안 연결 링크는 합친 노드 안으로 사라진다
    slot_keys = ["limit"] + [k for k, _, _ in SLOTS if k in its]
    ratio = {}
    for sk in slot_keys[1:]:
        by = defaultdict(list)
        for l in links:
            if l["id"] in its[sk] and l["max"] > 0 and not (l["len"] >= OUTLIER_LEN and its[sk][l["id"]] < OUTLIER_RATIO * l["max"]):
                by[l["rank"]].append(its[sk][l["id"]] / l["max"])
        ratio[sk] = {r: round(statistics.median(v), 3) for r, v in by.items() if len(v) >= 20}
    edges = []
    outl = {}
    cov = {sk: [0, 0.0] for sk in slot_keys}
    tot_len = sum(l["len"] for l in links)
    for l in links:
        lim = max(MIN_LIMIT, l["max"] or DEFAULT_KMH.get(l["rank"], 30))
        ts = []
        for sk in slot_keys:
            if sk == "limit":
                v = lim
                cov[sk][0] += 1
                cov[sk][1] += l["len"]
            elif l["id"] in its[sk] and not (l["len"] >= OUTLIER_LEN and its[sk][l["id"]] < OUTLIER_RATIO * lim):
                v = its[sk][l["id"]]
                cov[sk][0] += 1
                cov[sk][1] += l["len"]
            else:
                if l["id"] in its[sk]:
                    outl[sk] = outl.get(sk, 0) + 1
                v = lim * ratio[sk].get(l["rank"], 0.75)
            v = max(8.0, v)
            ts.append(max(1, round(l["len"] / (v / 3.6))))
        edges.append([node_ix[l["f"]], node_ix[l["t"]]] + ts)
    # 같은 교차로인데 번호가 달라 안 합쳐진 노드(30m 안)는 양방향으로 잇는다 — 회전 연결 링크가 한쪽만 있어
    # 코앞에서 수 km 를 돌아오는 경우가 있었다(연동면 강변길·청연로 교차로).
    cellmap = defaultdict(list)
    for i, (x, y) in enumerate(nodes):
        cellmap[(int(x * KX / JOIN_M), int(y * KY / JOIN_M))].append(i)
    njoin = 0
    for (gx, gy), lst in cellmap.items():
        for i in lst:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in cellmap.get((gx + dx, gy + dy), ()):
                        if j <= i:
                            continue
                        d = math.hypot((nodes[i][0] - nodes[j][0]) * KX, (nodes[i][1] - nodes[j][1]) * KY)
                        if d <= JOIN_M:
                            t = max(1, round(d / (JOIN_KMH / 3.6)))
                            edges.append([i, j] + [t] * len(slot_keys))
                            edges.append([j, i] + [t] * len(slot_keys))
                            njoin += 1
    # 1차로 시군도(교행·소방차 진입 주의) — 세종 안만
    narrow = []
    for l in links:
        if l["rank"] == "107" and l["lanes"] == 1:
            mx = sum(p[0] for p in l["pts"]) / len(l["pts"])
            my = sum(p[1] for p in l["pts"]) / len(l["pts"])
            if any(inside(mx, my, r) for r in dongs.outline):
                narrow.append(l["pts"] if len(l["pts"]) <= 4 else [l["pts"][0], l["pts"][len(l["pts"]) // 2], l["pts"][-1]])
    # 고속·도시고속 전용 노드는 건물·센터 접속에서 뺀다
    ok_node = [False] * len(nodes)
    for l in links:
        if l["rank"] not in ("101", "102"):
            ok_node[node_ix[l["f"]]] = ok_node[node_ix[l["t"]]] = True
    info = {"slots": slot_keys, "ratio": ratio, "snapshots": {k: v for k, v in meta.items()},
            "coverage": {sk: {"links": c[0], "len_pct": round(c[1] / tot_len * 100, 1)} for sk, c in cov.items()},
            "n_links": len(links), "km": round(tot_len / 1000), "n_conn": n_conn, "n_nodes": len(nodes), "n_join": njoin, "join_m": JOIN_M, "outliers": outl}
    return nodes, edges, ok_node, narrow, info


def dijkstra(n, adj, src):
    dist = [math.inf] * n
    dist[src] = 0
    h = [(0, src)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


class Grid:
    def __init__(self, nodes, ok):
        self.c = defaultdict(list)
        for i, (x, y) in enumerate(nodes):
            if ok[i]:
                self.c[(int(x * KX / 200), int(y * KY / 200))].append(i)
        self.nodes = nodes

    def near(self, x, y):
        gx, gy = int(x * KX / 200), int(y * KY / 200)
        best, bd = -1, math.inf
        for r in range(0, 12):
            for i in range(gx - r, gx + r + 1):
                for j in range(gy - r, gy + r + 1):
                    if max(abs(i - gx), abs(j - gy)) != r:
                        continue
                    for k in self.c.get((i, j), ()):
                        nx, ny = self.nodes[k]
                        d = math.hypot((nx - x) * KX, (ny - y) * KY)
                        if d < bd:
                            best, bd = k, d
            if best >= 0 and bd < r * 200:
                break
        return best, bd


def main():
    dongs = Dongs()
    dp, ym = dong_people(dongs.names)
    nodes, edges, ok, narrow, ninfo = network(dongs)
    n = len(nodes)
    # 센터에서 닿는 노드만 접속 후보로(경계상자 가장자리 막다른 링크 제외)
    adj = [[] for _ in range(n)]
    for e in edges:
        adj[e[0]].append((e[1], e[2]))
    st = load(os.path.join(DATA, "stations.json"))["stations"]
    g0 = Grid(nodes, ok)
    for s in st:
        s["node"], s["snap_m"] = g0.near(s["lon"], s["lat"])
    reach = [False] * n
    for s in st:
        for i, d in enumerate(dijkstra(n, adj, s["node"])):
            if d < math.inf:
                reach[i] = True
    ok2 = [a and b for a, b in zip(ok, reach)]
    grid = Grid(nodes, ok2)
    bl, stat = buildings(dongs, dp)
    acc_ms = ACCESS_KMH / 3.6
    for b in bl:
        k, d = grid.near(b["x"], b["y"])
        b["n"] = k
        b["ac"] = round(d * DETOUR / acc_ms)
    # 인구 배분: 행정동 인구를 주거 연면적 비례로(세대수 있으면 세대수로)
    w = defaultdict(float)
    for b in bl:
        if b["u"] in ("01", "02"):
            b["_w"] = b["hh"] * 80 if b["hh"] else b["a"]
            w[b["d"]] += b["_w"]
    for b in bl:
        nm = dongs.names[b["d"]]
        b["pp"] = round(dp[nm]["pop"] * b["_w"] / w[b["d"]], 1) if b.get("_w") and w[b["d"]] else 0
    # 격자 원점
    x0 = min(p[0] for r in dongs.outline for p in r)
    y0 = min(p[1] for r in dongs.outline for p in r)
    cell = lambda x, y: (int((x - x0) * KX // CELL), int((y - y0) * KY // CELL))
    cols = ["x", "y", "d", "u", "yr", "s", "fl", "a", "pp", "n", "ac", "c0", "c1", "c2", "c3", "c4", "gx", "gy"]
    sk = list(STRUCT)
    B = []
    for b in bl:
        gx, gy = cell(b["x"], b["y"])
        B.append([round(b["x"], 5), round(b["y"], 5), b["d"], b["u"], b["yr"], sk.index(b["s"]), b["fl"], b["a"], b["pp"],
                  b["n"], b["ac"]] + b["c"] + [gx, gy])
    N = [[round(x, 5), round(y, 5)] for x, y in nodes]
    ncell = [list(cell(x, y)) if ok2[i] else None for i, (x, y) in enumerate(nodes)]
    res = {
        "built": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cell": CELL, "origin": [x0, y0], "kx": KX, "ky": KY, "access_kmh": ACCESS_KMH, "detour": DETOUR,
        "stations": st, "nodes": N, "ncell": ncell, "edges": edges, "net": ninfo, "narrow": narrow,
        "bcols": cols, "b": B, "structs": [[k, STRUCT[k][0], STRUCT[k][1]] for k in sk],
        "uses": {k: list(v) for k, v in USE.items()},
        "dongs": [{"name": nm, "kind": kind, **dp[nm]} for nm, kind, _, _ in dongs.d], "pop_ym": ym,
        "stat": dict(stat), "n_b": len(B),
    }
    json.dump(res, open(os.path.join(DATA, "analysis.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("buildings", len(B), dict(stat))
    print("nodes", n, "reach", sum(ok2), "edges", len(edges), "narrow", len(narrow))
    print(ninfo["slots"], ninfo["coverage"], ninfo["ratio"])
    for s in st:
        print(s["name"], s["snap_m"] and round(s["snap_m"]))


if __name__ == "__main__":
    main()
