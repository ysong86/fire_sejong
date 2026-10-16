# -*- coding: utf-8 -*-
"""공용 encrypt_page.py 가 만든 문(site/index.html)을 화재안전 상황판에 맞게 고친다.

  python tools/gate_fix.py site/index.html

공용 문은 연구모임 상황판(생활권·상가공실) 기준이라 제작 표기·문구·미리보기 길이가 다르다.
화재안전은 교통안전 상황판처럼 도시안전연구센터 제작(사용자 지정 2026-10-16), 문의는 송양호.
"""
import sys

ORG = "세종연구원 도시안전연구센터"
MEMBERS = "안용준 센터장 · 송양호 책임연구위원 · 주재성 전문연구위원 · 최유라 전문연구위원"

p = sys.argv[1]
s = open(p, encoding="utf-8").read()
FIX = [
    ("연구모임 내부 검토용입니다.", "도시안전연구센터 내부 검토용입니다."),
    ('<span class="aside">연구원의 공식 업무가 아닌, 참여 연구자들의 호기심과 재미에서 시작한 작업입니다. 결과물은 참고용으로 봐 주세요.</span>', ""),
    ('제작: 세종연구원 연구모임<span class="names">김성표, 안용준, 김흥주, 남영식, 이재민, 이자은, 송양호</span>',
     f'제작: {ORG}<span class="names">{MEMBERS}</span>'),
    ("▶ 30초 미리보기", "▶ 40초 미리보기"),
    ("</head>", "<style>.foot .names{white-space:normal!important}</style></head>"),
]
for a, b in FIX:
    if a not in s:
        raise SystemExit("문 구조가 바뀌었습니다 — 못 찾음: " + a[:40])
    s = s.replace(a, b, 1)
open(p, "w", encoding="utf-8").write(s)
print("문 고침:", p)
