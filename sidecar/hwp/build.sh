#!/bin/sh
# HWP·HWPX 사이드카 빌드 — hwplib(spike/hwplib/RESULT.md)·hwpxlib
# (spike/hwpxlib/RESULT.md, QA(h) Phase 1) main 브랜치 빌드가 선행되어야 한다.
# 패키지명이 겹치지 않아(kr.dogfoot.hwplib vs kr.dogfoot.hwpxlib) 같은
# out/ 산출물 디렉터리 하나에 함께 컴파일한다.
set -e
cd "$(dirname "$0")"
HWPLIB=../../spike/hwplib/libs/hwplib-main
HWPXLIB=../../spike/hwpxlib/libs/hwpxlib-main
[ -d "$HWPLIB" ] || { echo "hwplib 빌드가 없습니다: $HWPLIB (spike/hwplib/RESULT.md 참고)"; exit 1; }
[ -d "$HWPXLIB" ] || { echo "hwpxlib 빌드가 없습니다: $HWPXLIB (spike/hwpxlib/RESULT.md 참고)"; exit 1; }
mkdir -p out
javac -encoding UTF-8 -cp "$HWPLIB:$HWPXLIB" -d out \
    HwpToText.java HwpToJson.java JsonToHwp.java LineSegDebug.java MakeFormattedHwp.java \
    HwpxToText.java HwpxToJson.java
echo "OK: sidecar/hwp/out"
