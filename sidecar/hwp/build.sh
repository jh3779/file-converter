#!/bin/sh
# HWP·HWPX 사이드카 빌드 — hwplib(spike/hwplib/RESULT.md)·hwpxlib
# (spike/hwpxlib/RESULT.md, QA(h) Phase 1) main 브랜치 빌드가 선행되어야 한다.
# 패키지명이 겹치지 않아(kr.dogfoot.hwplib vs kr.dogfoot.hwpxlib) 같은
# out/ 산출물 디렉터리 하나에 함께 컴파일한다.
#
# hwpxlib은 선택 사항이다 — app/converters/hwp.py의 _classpath()가 hwpxlib
# 없이도 HWP 경로만으로 조용히 동작하도록 설계돼 있으므로(HWPX 지원 이전
# 기존 개발 환경과의 호환), hwpxlib 빌드가 없으면 HwpxToText/HwpxToJson만
# 빼고 HWP 사이드카는 그대로 빌드한다.
set -e
cd "$(dirname "$0")"
HWPLIB=../../spike/hwplib/libs/hwplib-main
HWPXLIB=../../spike/hwpxlib/libs/hwpxlib-main
[ -d "$HWPLIB" ] || { echo "hwplib 빌드가 없습니다: $HWPLIB (spike/hwplib/RESULT.md 참고)"; exit 1; }
mkdir -p out
SOURCES="HwpToText.java HwpToJson.java JsonToHwp.java LineSegDebug.java MakeFormattedHwp.java PageBreakDebug.java"
CP="$HWPLIB"
if [ -d "$HWPXLIB" ]; then
    SOURCES="$SOURCES HwpxToText.java HwpxToJson.java MakeTabHwpx.java"
    CP="$HWPLIB:$HWPXLIB"
else
    echo "hwpxlib 빌드가 없습니다: $HWPXLIB (spike/hwpxlib/RESULT.md 참고) — HWPX 사이드카는 건너뜁니다"
fi
javac -encoding UTF-8 -cp "$CP" -d out $SOURCES
echo "OK: sidecar/hwp/out"
