# -*- coding: utf-8 -*-
"""화재안전 상황판 기능 소개 영상(약 40초, MP4) — 로그인 문에서 '미리보기'로 공개한다.

  python tools/make_video.py
    입력: http://127.0.0.1:8772/dashboard.html (launch.json sejong-fire 서버, 평문은 로컬에만)
    출력: docs/화재안전상황판_소개.mp4 + site/preview.mp4

공개 영상이라 지표 숫자·표 수치·건물 정보값·발견 문장은 흐리게 처리한다(기능·화면 구성·지도 색은 보이게).
녹화 방식은 상가공실 상황판 tools/make_video.py 와 같다(설치된 Chrome, 가짜 포인터·클릭 물결·자막, hits.sh 차단).
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "http://127.0.0.1:8772/dashboard.html"
TMP = os.path.join(HERE, "data", "video_tmp")
OUT = os.path.join(HERE, "docs", "화재안전상황판_소개.mp4")
SITE = os.path.join(HERE, "site", "preview.mp4")
W, H = 1440, 810

BLUR = r"""
(() => {
  const css = document.createElement('style');
  css.textContent = `
  .kpi .v,table.t td.r,#finds p,#finds h3,#method table td.r,#mapnote,.maplibregl-popup-content td.r,.maplibregl-popup-content .tt,
  .virt .vi span{filter:blur(5px)!important}`;
  document.head.appendChild(css);
})();
"""

OVERLAY = r"""
(() => {
  const css = document.createElement('style');
  css.textContent = `
  #vcur{position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;
        transform:translate(-3px,-2px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
  .vring{position:fixed;width:46px;height:46px;margin:-23px 0 0 -23px;border-radius:50%;border:3px solid #B03A3A;
         z-index:2147483646;pointer-events:none;animation:vr .6s ease-out forwards}
  @keyframes vr{from{transform:scale(.3);opacity:.9}to{transform:scale(1.4);opacity:0}}
  #vcap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2147483645;pointer-events:none;
        background:rgba(21,35,42,.9);color:#fff;font:700 21px/1.3 "IBM Plex Sans KR","Malgun Gothic",sans-serif;
        padding:10px 22px;border-radius:999px;letter-spacing:-.01em;opacity:0;transition:opacity .35s;white-space:nowrap}
  #vcap small{font-weight:400;font-size:15px;opacity:.85;margin-left:10px}
  html{scroll-behavior:auto!important}`;
  document.head.appendChild(css);
  const c = document.createElement('div'); c.id = 'vcur';
  c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M4 2l15 9.5-6.6 1.6 3.9 7.4-3.1 1.6-3.9-7.5L4 19.5z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  document.body.appendChild(c);
  const cap = document.createElement('div'); cap.id = 'vcap'; document.body.appendChild(cap);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = 'vring';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.body.appendChild(r); setTimeout(() => r.remove(), 700);
  }, true);
  window.__cap = (t, s) => { cap.innerHTML = t + (s ? '<small>' + s + '</small>' : ''); cap.style.opacity = t ? 1 : 0; };
  window.__scroll = (y, ms) => new Promise(res => {
    const y0 = scrollY, t0 = performance.now(), ease = t => t < .5 ? 2*t*t : 1 - Math.pow(-2*t + 2, 2) / 2;
    (function step(now){ const k = Math.min(1, (now - t0) / ms); scrollTo(0, y0 + (y - y0) * ease(k));
      k < 1 ? requestAnimationFrame(step) : res(); })(t0);
  });
  window.__top = sel => { const el = document.querySelector(sel); return el ? el.getBoundingClientRect().top + scrollY : 0; };
})();
"""


def main():
    os.makedirs(TMP, exist_ok=True)
    for f in glob.glob(os.path.join(TMP, "*.webm")):
        os.remove(f)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light",
                            record_video_dir=TMP, record_video_size={"width": W, "height": H})
        ctx.route("**/hits.sh/**", lambda r: r.abort())          # 녹화가 실제 조회수를 올리지 않게
        ctx.add_init_script("try{localStorage.clear()}catch(e){}")
        ctx.add_init_script(f"document.addEventListener('DOMContentLoaded', () => {{ {BLUR} }});")
        pg = ctx.new_page()
        t_open = time.time()                      # 녹화는 페이지가 생길 때 시작한다
        pg.goto(SRC, wait_until="networkidle")
        pg.wait_for_function("window.__fire && window.__fire.map.isStyleLoaded() && document.querySelectorAll('.kpi').length === 5", timeout=60000)
        pg.evaluate(OVERLAY)
        pg.mouse.move(W * 0.55, H * 0.45)
        pg.wait_for_timeout(1200)
        start = time.time() - t_open

        segs = []                                   # 영상에 남길 구간(녹화 시각 기준) — 계산·지도 그리기 대기는 잘라낸다

        def now():
            return time.time() - t_open

        def hold(ms):
            t0 = now()
            pg.wait_for_timeout(ms)
            segs.append((t0, now()))

        def settle():
            pg.wait_for_function("!document.getElementById('loading').classList.contains('on')", timeout=60000)
            pg.evaluate("() => new Promise(r => { const m = window.__fire.map; if (m.loaded() && !m.isMoving()) r(); else m.once('idle', r); setTimeout(r, 15000); })")
            pg.wait_for_timeout(150)

        def cap(t, s=""):
            pg.evaluate("([t,s]) => __cap(t,s)", [t, s])

        def scroll_to(sel, ms, off=70):
            y = pg.evaluate(f"__top('{sel}')") - off
            t0 = now()
            pg.evaluate(f"__scroll({max(0, y)}, {ms})")
            pg.wait_for_timeout(ms + 50)
            segs.append((t0, now()))

        def move(sel, steps=18, click=True, dx=0.5, dy=0.5):
            box = pg.locator(sel).first.bounding_box()
            x, y = box["x"] + box["width"] * dx, box["y"] + box["height"] * dy
            t0 = now()
            pg.mouse.move(x, y, steps=steps)
            if click:
                pg.mouse.down()
                pg.mouse.up()
                pg.wait_for_timeout(250)          # 클릭 물결이 보이게
            segs.append((t0, now()))
            if click:
                settle()
            return x, y

        def jump(center, zoom):
            pg.evaluate(f"() => window.__fire.map.jumpTo({{center: {center}, zoom: {zoom}}})")
            settle()

        # 제목·추정 고지
        cap("세종 화재안전 상황판", "소방차 도달시간 × 건물 화재위험")
        hold(2200)
        cap("화재 지점은 비공개라", "위험은 연구진 추정 — 상단에 밝혀 둡니다")
        move("#notice", steps=16, click=False, dx=.3)
        hold(1800)
        move(".kpi:nth-child(2)", steps=14, click=False)
        hold(500)

        # 1차 도착시간
        cap("119안전센터에서 몇 분 만에 닿나", "ITS 실측 도로 속도로 계산한 주행시간")
        scroll_to(".mapgrid", 900, 150)
        settle()
        hold(1600)
        jump("[127.275, 36.50]", 12.2)
        hold(2000)
        cap("시간대를 바꾸면", "제한속도로 달릴 때와 실제 속도의 차이")
        move("#slot", steps=14, click=False)
        pg.select_option("#slot", "limit")
        settle()
        hold(1500)
        pg.select_option("#slot", index=len(pg.locator("#slot option").all()) - 1)
        settle()
        hold(1000)

        # 2차 출동
        jump("[127.27, 36.56]", 10.3)
        cap("2차 출동", "가까운 센터가 비었을 때 두 번째 센터에서 오는 시간")
        move('#modes [data-m="second"]', steps=16)
        hold(2400)

        # 건물 위험
        cap("건물 화재위험(추정)", "용도·노후도·구조·거주자·규모 다섯 요소")
        move('#modes [data-m="risk"]', steps=14)
        hold(1800)
        cap("가중치를 바꾸면 바로 다시 계산", "예: 인명 중심")
        move('#presets [data-p="1"]', steps=18)
        hold(1800)

        # 이변량
        cap("위험은 높은데 늦게 닿는 곳", "빨간 테두리 = 우선 대상")
        move('#modes [data-m="biv"]', steps=18)
        hold(2000)
        jump("[127.215, 36.595]", 13.2)
        hold(1500)
        pt = pg.evaluate("""() => { const m = window.__fire.map, c = m.getCanvas().getBoundingClientRect();
            const fs = m.queryRenderedFeatures([[c.width*.3, c.height*.3], [c.width*.7, c.height*.7]], {layers: ['bld']});
            if (!fs.length) return null; const p = m.project(fs[0].geometry.coordinates); return [c.left + p.x, c.top + p.y]; }""")
        if pt:
            cap("건물을 누르면", "도착시간·위험 점수와 그 근거")
            t0 = now()
            pg.mouse.move(pt[0], pt[1], steps=16)
            pg.mouse.down()
            pg.mouse.up()
            segs.append((t0, now()))
            pg.wait_for_timeout(400)
            hold(2400)
            pg.evaluate("() => document.querySelectorAll('.maplibregl-popup').forEach(p => p.remove())")

        # 가상 119지역대
        jump("[127.27, 36.58]", 10.6)
        cap("가상 119지역대 놓기", "지도를 누르면 그 자리에 거점이 생긴 것으로 다시 계산")
        move("#addv", steps=16, click=False)
        pg.locator("#addv").click()
        hold(600)
        box = pg.locator("#map").bounding_box()
        t0 = now()
        pg.mouse.move(box["x"] + box["width"] * .44, box["y"] + box["height"] * .30, steps=18)
        pg.mouse.down()
        pg.mouse.up()
        pg.wait_for_timeout(250)
        segs.append((t0, now()))
        settle()
        hold(1200)
        cap("지표가 얼마나 좋아지는지 바로 보여 줍니다", "")
        scroll_to("#kpis", 700, 40)
        hold(1600)

        # 표·방법
        cap("읍면동별 진단 · 출동 거점별 담당", "")
        pg.mouse.move(W * 0.92, H * 0.4, steps=8)
        scroll_to("#dongtab", 1000, 120)
        hold(1400)
        cap("쓴 자료와 가정을 모두 밝혔습니다", "ITS 속도 반영·도로망 손질·위험 점수 기준")
        scroll_to("#method", 900, 90)
        hold(1600)
        cap("도시안전연구센터 내부 검토용", "비밀번호 문의: 송양호(ysong@sri.re.kr)")
        hold(2000)

        end = time.time() - t_open
        video = pg.video.path()
        ctx.close()
        b.close()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    # 붙어 있는 구간은 합친다
    merged = []
    for t0, t1 in sorted(segs):
        if merged and t0 - merged[-1][1] < 0.08:
            merged[-1] = (merged[-1][0], t1)
        else:
            merged.append((t0, t1))
    dur = sum(t1 - t0 for t0, t1 in merged)
    parts = "".join(f"[0:v]trim=start={t0:.3f}:end={t1:.3f},setpts=PTS-STARTPTS[v{i}];" for i, (t0, t1) in enumerate(merged))
    fc = parts + "".join(f"[v{i}]" for i in range(len(merged))) + f"concat=n={len(merged)}:v=1:a=0,fps=30,format=yuv420p[out]"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cmd = [ff, "-y", "-i", video, "-filter_complex", fc, "-map", "[out]", "-c:v", "libx264", "-preset", "slow", "-crf", "24",
           "-movflags", "+faststart", "-an", OUT]
    subprocess.run(cmd, check=True, capture_output=True)
    os.makedirs(os.path.dirname(SITE), exist_ok=True)
    shutil.copyfile(OUT, SITE)
    print(f"영상: {OUT}  ({dur:.1f}초, 구간 {len(merged)}개, 녹화 {end - start:.1f}초, {os.path.getsize(OUT) / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
