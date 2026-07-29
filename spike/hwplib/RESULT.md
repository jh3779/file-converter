# hwplib 기술 스파이크 결과

> 2026-07-29 · OQ-001 검증 · 환경: macOS(Apple Silicon), OpenJDK 26, hwplib 1.1.10(Maven) + main 브랜치(d9e073d) 소스 빌드

## 결론: **통과** — HWP 지원(REQ-F-005)은 Must 유지 가능

## 검증 항목별 결과

### 1. 읽기 성공률: 11/11
표·그림·수식·각주미주·차트·글상자·머리글꼬리글·문단번호·셀병합·대용량 등 공식 샘플 전부 파싱 성공. 한글 텍스트 깨짐 없음.

### 2. 텍스트·표 추출 품질
- 표 셀 내용 추출됨 (`TextExtractor` + `InsertControlTextBetweenParagraphText`). 셀 단위 구조 접근은 `ControlTable` 객체 모델로 가능 (행/열/병합 정보 보존).
- 수식은 HWP 수식 스크립트 텍스트(`(a+b) ^{2} =...`)로 추출.
- main 브랜치는 문단번호(개요 번호)까지 추출 (1.1.10은 미포함).
- 그림·차트는 텍스트 없음이 정상 (바이너리는 BinData로 접근 가능 — 개수 확인됨).

### 3. 성능
147,456 문단 / 193만 자 대용량 파일 읽기 **189ms**. 성능 리스크 없음.

### 4. 쓰기 (수정·생성)
- 라운드트립(읽기→저장→재읽기→텍스트 비교): 표·그림·셀병합 3/3 **텍스트 동일**.
- 신규 생성(BlankFileMaker → 텍스트 삽입 → 저장 → 재읽기): **내용 일치**. 4.6KB 정상 HWP 생성.

## 주의점 (구현 시 반영)

| 항목 | 내용 |
|------|------|
| 버전 선택 | Maven 최신 릴리스 1.1.10(2025-05)에는 **Scripts 스트림 없는 파일 재읽기 버그** 있음 (라운드트립 실패 재현됨). main 브랜치(d9e073d)에서 수정 확인 → **소스 빌드로 사용** (다음 릴리스 나오면 교체) |
| JDK 호환 | JDK 11+ 컴파일 시 legacy import 2건 패치 필요: `javax.xml.bind.DatatypeConverter` → `java.util.Base64`, `com.sun.jmx.*` 불용 import 제거 (이번 스파이크에서 패치 완료, 컴파일 에러 0) |
| 의존성 | **외부 의존성 0** — Apache POI(POIFS)가 `kr.dogfoot.hwplib.org.apache.poi`로 shading되어 JAR 하나로 완결. 사이드카 번들 단순 |
| 라이선스 | Apache-2.0 (POM 확인). 고지문만 포함하면 상업 배포 무관 |
| HWP→PDF 경로 | hwplib은 파싱/객체모델까지. 렌더링은 별도 — 파이프라인: HWP →(hwplib)→ 구조 추출 → DOCX 생성 → LibreOffice → PDF. ※ LibreOffice 자체 HWP 필터는 구형 HWP 3.x 전용이라 hwplib 경로가 필수 |
| 실사용 파일 검증 | 공식 샘플은 통과. 실제 공공기관·회사 HWP(복잡한 서식·배포용 문서 포함)로 추가 검증 권장. 배포용 문서(distribution.hwp)는 별도 읽기 API(`Reading_Distribution_HWPFile` 참고) 존재 |

## 산출물
- `Spike.java` — 읽기/추출/구조/라운드트립 검증
- `SpikeCreate.java` — 신규 생성 검증
- `libs/hwplib-main/` — main 브랜치 패치 빌드 (JDK 26)
- `output/` — 라운드트립·생성 결과 HWP (한컴오피스/한컴독스에서 육안 확인 권장)

## 실행 방법
```bash
cd spike/hwplib
javac -encoding UTF-8 -cp libs/hwplib-main -d out Spike.java SpikeCreate.java
java -cp "out:libs/hwplib-main" Spike repo/sample_hwp output
java -cp "out:libs/hwplib-main" SpikeCreate output
```
