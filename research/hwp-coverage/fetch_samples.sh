#!/bin/sh
# OQ-006 실사용 HWP 샘플 확보 — 공공기관이 웹에 공개 배포 중인 서식/문서.
# 실제 .hwp 파일은 저장소에 커밋하지 않는다(제3자 문서, 재배포 불필요) — 이 스크립트로 재현.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIR="$SCRIPT_DIR/samples"
mkdir -p "$DIR"
cd "$DIR"

# 서명 검증 실패(HTTP 200 + 에러 HTML 응답 등 소프트 실패 포함) 시 즉시 중단.
# OLE/HWP 5.x 컴파운드 파일 시그니처: D0 CF 11 E0
fetch() {
  name="$1"; url="$2"
  curl -fsSL -o "$name" "$url"
  sig=$(head -c 4 "$name" | xxd -p)
  if [ "$sig" != "d0cf11e0" ]; then
    echo "실패: $name 서명 불일치 ($sig) — HWP 파일이 아닌 응답을 받았습니다: $url" >&2
    rm -f "$name"
    exit 1
  fi
  echo "OK: $name ($sig)"
}

fetch unikorea-contract.hwp \
  "https://www.unikorea.go.kr/web/unikorea/file/download/uu/2020020316390107568.hwp"
fetch kma-postcard.hwp \
  "https://www.kma.go.kr/kma/servlet/NeoboardProcess?mode=download&bid=gongzi&num=1192291&fno=2&callback=&ses=USER_SESSION&k=ATC201805021340272_89f4662d-75e6-4c33-b54a-7ffc16e0bcd8.hwp"
fetch mois-hwpplan.hwp \
  "https://www.mois.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_00088283D0m14VL&fileSn=0"
fetch incheon-gongmun.hwp \
  "https://incheon.korcham.net/file/dext5uploaddata/2018/07/%EB%B0%9C%EC%86%A1%EA%B3%B5%EB%AC%B8(%EB%B9%84%EC%A6%88%EB%8B%88%EC%8A%A4%EB%94%94%EB%A0%89%ED%86%A0%EB%A6%AC).hwp"
fetch jecheon-file2997.hwp \
  "https://www.jecheon.go.kr/site/www/download/file2997.hwp"

echo "다운로드 및 서명 검증 완료: 5개 파일"

# 6번째 샘플(distribution.hwp)은 공공기관 배포 파일이 아니라 hwplib 저장소의
# 자체 샘플이라 별도 클론이 필요하다 — 이 스크립트로는 받지 않는다.
DIST_SAMPLE="$SCRIPT_DIR/../../spike/hwplib/repo/sample_hwp/distribution.hwp"
if [ -f "$DIST_SAMPLE" ]; then
  echo "OK: distribution.hwp 확인됨 ($DIST_SAMPLE)"
else
  echo "안내: distribution.hwp가 없습니다. 다음으로 별도 확보하세요:" >&2
  echo "  git clone https://github.com/neolord0/hwplib spike/hwplib/repo" >&2
fi
