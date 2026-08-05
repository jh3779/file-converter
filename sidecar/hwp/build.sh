#!/bin/sh
# HWP 사이드카 빌드 — hwplib main 브랜치 빌드(spike/hwplib/RESULT.md 절차)가 선행되어야 한다.
set -e
cd "$(dirname "$0")"
HWPLIB=../../spike/hwplib/libs/hwplib-main
[ -d "$HWPLIB" ] || { echo "hwplib 빌드가 없습니다: $HWPLIB (spike/hwplib/RESULT.md 참고)"; exit 1; }
mkdir -p out
javac -encoding UTF-8 -cp "$HWPLIB" -d out HwpToText.java HwpToJson.java JsonToHwp.java LineSegDebug.java MakeFormattedHwp.java
echo "OK: sidecar/hwp/out"
