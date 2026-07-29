#!/bin/sh
# OQ-006 실사용 HWP 샘플 확보 — 공공기관이 웹에 공개 배포 중인 서식/문서.
# 실제 .hwp 파일은 저장소에 커밋하지 않는다(제3자 문서, 재배포 불필요) — 이 스크립트로 재현.
set -e
DIR="$(dirname "$0")/samples"
mkdir -p "$DIR"
cd "$DIR"

curl -sL -o unikorea-contract.hwp \
  "https://www.unikorea.go.kr/web/unikorea/file/download/uu/2020020316390107568.hwp"
curl -sL -o kma-postcard.hwp \
  "https://www.kma.go.kr/kma/servlet/NeoboardProcess?mode=download&bid=gongzi&num=1192291&fno=2&callback=&ses=USER_SESSION&k=ATC201805021340272_89f4662d-75e6-4c33-b54a-7ffc16e0bcd8.hwp"
curl -sL -o mois-hwpplan.hwp \
  "https://www.mois.go.kr/cmm/fms/FileDown.do?atchFileId=FILE_00088283D0m14VL&fileSn=0"
curl -sL -o incheon-gongmun.hwp \
  "https://incheon.korcham.net/file/dext5uploaddata/2018/07/%EB%B0%9C%EC%86%A1%EA%B3%B5%EB%AC%B8(%EB%B9%84%EC%A6%88%EB%8B%88%EC%8A%A4%EB%94%94%EB%A0%89%ED%86%A0%EB%A6%AC).hwp"
curl -sL -o jecheon-file2997.hwp \
  "https://www.jecheon.go.kr/site/www/download/file2997.hwp"

echo "다운로드 완료. 서명 확인(D0CF11E0 = 정상 OLE/HWP):"
for f in *.hwp; do
  sig=$(head -c 4 "$f" | xxd -p)
  echo "  $f: $sig"
done
