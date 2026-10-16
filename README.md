# 세종 화재안전 상황판

119안전센터에서 건물까지 소방차 주행시간(ITS 실측 속도)과 건물 화재위험(연구진 추정)을 겹쳐,
위험은 높은데 늦게 닿는 곳을 찾는 상황판. 지역안전지수 화재 분야용.

## 만드는 순서

```
C:\Python313\python.exe tools\fetch_buildings.py     # 브이월드 건물 외곽선(세종 전역, 타일 캐시) — 처음 한 번
C:\Python313\python.exe tools\fetch_ledger.py        # 건축물대장 표제부(법정동별 캐시) — 처음 한 번
C:\Python313\python.exe tools\build_network.py       # 전국표준노드링크 → data/network.json — 노드링크 판이 바뀌면
C:\Python313\python.exe tools\geocode_stations.py    # 119안전센터 좌표 — 목록이 바뀌면
C:\Python313\python.exe tools\collect_its.py --loop 30   # ITS 속도 표본(시간대별로 쌓임)
C:\Python313\python.exe analyze.py                   # → data/analysis.json
C:\Python313\python.exe build.py                     # → dashboard.html (평문)
```

**비공개(비밀번호)** — 사용자 결정(2026-10-16): 건물별 위험이 검증 전 추정이라. 비밀번호는 생활권 config page_password.

```
C:\Python313\python.exe tools\make_video.py        # 42초 미리보기(수치 흐림) → site/preview.mp4 (sejong-fire 서버 8772 필요)
C:\Python313\python.exe ..\sejong_livingzone\tools\encrypt_page.py dashboard.html site/index.html "세종 화재안전 상황판" --video preview.mp4 --contact "송양호(ysong@sri.re.kr)" --hits "https://hits.sh/ysong86.github.io/fire_sejong.svg?view=today-total&style=flat-square&label=%EC%A1%B0%ED%9A%8C%EC%88%98&color=1d5c7c&labelColor=64748b" --nav fire
sed -i 's/▶ 30초 미리보기/▶ 40초 미리보기/' site/index.html   # 문 버튼 문구가 공용 도구에 30초로 박혀 있다
```
→ gh-pages 에 site/index.html + preview.mp4 + .nojekyll 한 커밋. **dashboard.html(평문)·data/·docs/ 는 올리지 않는다.**

## 알아둘 것

- 키: 브이월드·포털은 `../sejong_livingzone/config.json`, ITS 는 `../sejong_traffic/config.json` (월 15,000건, 교통 상황판 NAS 수집과 같이 씀).
- 표준노드링크(2026-10-14 판)는 교차로를 진입 방향별 노드(앞 8자리 같음)로 쪼갠다 → analyze.py 가 앞 8자리로 합치고, 30m 안 노드는 잇는다.
  안 그러면 코앞에서 수 km 를 돌아 나오는 건물이 생긴다(연동면 강변길 70분).
- ITS 속도: 200m 넘는 링크인데 제한속도 25% 미만이면 이상치. 실측 없는 링크는 같은 시간대·등급의 실측/제한속도 중앙값을 곱한다.
  제한속도 10~20 으로 등록된 단지·둔치 도로는 30 으로 본다.
- 화재 발생 지점은 비공개 → 위험 점수는 추정. 화면 상단 고지문은 사용자 요청 문구.
- 119지역대는 공식 목록이 없어 OSM 위치(기본 계산에서 제외, 칩으로 켬). 금남면 지역대는 위치 미확인.
- 소화전(소방청 세종 소방용수 2021)은 좌표가 없어 미사용. 전국소방용수시설표준데이터 API(tn_pubr_public_ffus_wtrcns_api)는 활용신청 필요(현재 403).
