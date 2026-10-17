# -*- coding: utf-8 -*-
"""다음 날 아침까지 기다린다(그동안 PC 가 절전에 들지 않게 요청) → 출근 시간대 ITS 표본이 모이면 끝난다.

  python tools/wait_morning.py 10:05
  python tools/wait_morning.py 2026-10-19 20:05

SetThreadExecutionState 는 이 프로그램이 살아 있는 동안만 유효하다(Windows 전원 설정은 바꾸지 않는다).
"""
import ctypes
import datetime as dt
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

arg = " ".join(sys.argv[1:]) or "10:05"
now = dt.datetime.now()
if len(arg) > 5:                      # "2026-10-19 20:05" — 날짜까지
    target = dt.datetime.strptime(arg, "%Y-%m-%d %H:%M")
else:                                 # "10:05" — 다음에 오는 그 시각
    hh, mm = map(int, arg.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
print("기다림:", target, flush=True)
while dt.datetime.now() < target:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    time.sleep(60)
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
snaps = sorted(os.path.basename(f) for f in glob.glob(os.path.join(HERE, "data", "raw", "its", "*.json")))
wd = [s for s in snaps if dt.datetime.strptime(s[:8], "%Y%m%d").weekday() < 5]
am = [s for s in wd if s[9:11] in ("07", "08", "09")]
pm = [s for s in wd if s[9:11] in ("17", "18", "19")]
print("표본", len(snaps), "평일 출근", len(am), "평일 퇴근", len(pm), am + pm, flush=True)
