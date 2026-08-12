# hwpxlib 기술 스파이크 결과 — QA(h) HWPX 지원 Phase 1(읽기)

> 2026-08-07 · 외부 QA 피드백("hwpx도 지원하면 좋겠다") · 환경: macOS(Apple
> Silicon), OpenJDK 26, hwpxlib main 브랜치(473d9d6) 소스 빌드

## 결론: **통과** — HWPX 읽기 지원 가능, Phase 1(TXT/DOCX/PDF) 착수

## 배경

HWPX(확장자 `.hwpx`)는 한글과컴퓨터의 최신 표준 문서 포맷으로, 이 프로젝트가
지금까지 다뤄온 바이너리 `.hwp`(hwplib이 다루는 스펙)와는 **완전히 다른
스펙**이다(OWPML, ZIP 컨테이너 안에 XML — DOCX/PPTX와 구조적으로 비슷함).
hwplib 저장소 README 자체가 "hwpx 파일에 대한 라이브러리는
https://github.com/neolord0/hwpxlib 을 참조해 주세요"라고 명시해, hwplib으로
hwpx를 열 수 없다는 걸 먼저 확인했다.

## 검증 항목별 결과

### 1. 라이브러리 선택
`hwpxlib`(neolord0 — hwplib과 같은 저자)을 채택. 근거:
- **라이선스**: Apache-2.0(license.txt·pom.xml 둘 다 확인) — 이 프로젝트의
  라이선스 정책과 일치.
- **의존성**: pom.xml에 런타임 의존성이 **0개**(JUnit/Hamcrest는 test scope
  뿐)다 — hwplib과 마찬가지로 사이드카 번들이 단순해진다.
- **유지보수**: 커밋 이력이 스파이크 시점 기준 전날(2026-08-06)까지 있음 —
  활발히 유지되는 프로젝트.
- **API 유사성**: `HWPXReader.fromFilepath()` → `HWPXFile`, hwplib의
  `HWPReader.fromFile()` → `HWPFile`과 거의 1:1 대응. 내장 `TextExtractor`도
  같은 패턴(`TextExtractor.extract(file, method, insertParaHead, marks)`).

### 2. 컴파일
Java 7 source/target(pom.xml), 순수 JDK 소스라 **패치 없이** 바로
`javac`로 컴파일됨(hwplib은 JDK11+ 컴파일 시 legacy import 2건 패치가
필요했던 것과 대조적 — spike/hwplib/RESULT.md 참고).

### 3. 텍스트 추출 품질
`testFile/tool/textextractor/multipara.hwpx`(실제 뉴스 기사 원문, 공식
JUnit 테스트 `TestTextExtractor1`의 입력)로 검증 — 추출된 텍스트가 그
테스트가 기대하는 원문과 완전히 일치함을 직접 실행해 확인.

### 4. 구조(문단/런/표) 접근성 — HwpToJson.java와 동등한 스키마를 낼 수 있는지
- **문단→런→런아이템** 구조가 hwplib보다 단순하다: hwplib은 문단 안 위치를
  `HWPChar.getCharSize()` 가중치로 역산해야 서식 경계를 알 수 있었는데
  (DEC-027에서 실제 버그가 났던 지점), HWPX는 **각 Run이 자기 charPrIDRef를
  직접 갖고 있어** run 경계가 이미 XML 구조 자체에 있다 — 위치 역산이
  필요 없음.
- **표**: `Table`이 hwplib처럼 별도 컨트롤 목록이 아니라 **RunItem으로
  문단 안에 직접** 들어간다(한 문단에 텍스트와 표가 섞여 있을 수 있음 —
  구현 시 반영). `Tc.cellAddr()`/`cellSpan()`으로 셀 위치·병합 정보 접근
  가능(이번 phase는 hwplib DEC-028 초기와 같은 원칙으로 병합 정보는 아직
  안 씀 — 셀 텍스트만 평문 추출).
- **문자 서식**: `CharPr.bold()/italic()/underline()/height()/textColor()`가
  hwplib의 `CharShape`와 거의 1:1 대응. **버그 1건 발견·수정**: `bold()`/
  `italic()`은 속성 존재 자체가 신호(null이면 없음, `NoAttributeNoChild`
  타입)라 `!= null` 체크가 맞지만, `underline()`은 "밑줄 없음"도 명시적
  객체(`Underline{type=NONE}`)로 표현돼 있어 똑같이 `!= null`로 체크하면
  **모든 run이 밑줄 있음으로 잘못 나온다** — 서로 다른 두 샘플 파일에서
  전부 재현해 발견, `underline().type() != UnderlineType.NONE`으로 수정.

### 5. 실사용 샘플 크래시 검증
`testFile/reader_writer/`의 실제 hwpxlib 테스트 픽스처(SimpleTable·
HeaderFooter·MultiColumn·PageFunctions·ChangeTrack·SimpleEdit 등, hwpxlib
자체 read/write 회귀 테스트에 쓰이는 파일들) 전부 크래시 없이 읽힘 확인.
HeaderFooter·SimpleEdit는 본문 블록이 0개로 나오는데, 이건 실패가 아니라
**머리말/꼬리말 텍스트가 이번 phase 범위 밖**이라는 뜻(hwplib 쪽
`emitParagraph`의 재귀 컨트롤 처리 — 외부 QA #43, DEC-032 — 와 동등한
확장은 후속 과제로 문서화).

## 알려진 한계 (Phase 1, 정직하게 문서화)
- 표 셀 병합(colSpan/rowSpan) 미반영 — hwplib 쪽 DEC-028 초기와 같은 원칙.
- 머리말·꼬리말·각주·미주·글상자 텍스트 미반영 — hwplib 쪽 DEC-032가
  해결한 문제의 HWPX판이 아직 없음.
- 문단 정렬·쪽 나눔 등 문단 단위 서식 미반영 — hwplib 쪽도 DEC-040(이번
  세션 별도 브랜치) 이전엔 마찬가지였음.
- 표 안에 중첩된 표는 미반영(셀 텍스트 추출이 재귀하지 않음).
- **쓰기(HWPX 생성) 자체가 이번 phase 범위 밖** — DOCX→HWPX 등은 사용자와
  합의한 후속 phase.

## 산출물
- `Spike.java` — 읽기·텍스트 추출 검증
- `libs/hwpxlib-main/` — main 브랜치 빌드(JDK 26, 패치 불요)
- 실제 사이드카 코드는 `sidecar/hwp/HwpxToText.java`·`HwpxToJson.java`
  (hwplib과 패키지명이 겹치지 않아 같은 사이드카 디렉터리에 둠)

## 실행 방법 (로컬 재현)
```bash
cd spike/hwpxlib
git clone https://github.com/neolord0/hwpxlib.git repo
mkdir -p libs/hwpxlib-main
find repo/src/main/java -name "*.java" > repo/sources.txt
javac -encoding UTF-8 -nowarn -d libs/hwpxlib-main @repo/sources.txt
javac -encoding UTF-8 -cp libs/hwpxlib-main -d out Spike.java
java -cp "out:libs/hwpxlib-main" Spike repo/testFile/tool/textextractor/multipara.hwpx
```

---

# Phase 2(쓰기) — DOCX/PDF → HWPX

> 2026-08-11 · 사용자와 합의한 HWPX 쓰기 방향 착수 전 스파이크 · 환경:
> macOS(Apple Silicon), OpenJDK 26, hwpxlib main 브랜치 소스 빌드(Phase 1과
> 동일 `libs/hwpxlib-main`)

## 결론: **통과** — 3가지 API 불확실성 전부 write→read 왕복으로 확정, 본
기능(`JsonToHwpx.java`) 착수 가능

## 검증 항목별 결과

### 1. 쪽 나눔 필드: `ParaPr.breakSetting().pageBreakBefore()` vs `Para.pageBreak()`
두 필드 모두 **독립적으로 정확히 왕복**됨을 직접 확인 — 한 문서 안에 각각만
켠 문단을 따로 만들어 재읽기했더니 서로 침범 없이 정확히 분리 보존됨:
```
para 1 (A만 켬): breakSetting.pageBreakBefore=true  para.pageBreak=false
para 2 (B만 켬): breakSetting.pageBreakBefore=false para.pageBreak=true
```
**채택: `ParaPr.breakSetting().pageBreakBefore()`(후보 A)**. 근거: 클래스
필드 주석이 "문단 앞에서 항상 쪽 나눔 여부"로, DEC-039에서 hwplib
`ParaShapeProperty1.setSplitPageBeforePara()`("문단 앞에서 항상 쪽 나눔")와
문구가 정확히 일치한다 — HWP 쪽에서 이미 검증된 의미론과 대칭. `Para
.pageBreak()`는 필드 주석이 "쪽 나눔 여부"로만 돼 있어 의미가 더 모호함
(문단 자체가 쪽 경계에 걸쳐 있다는 표시일 가능성 등). hwpxlib API/실사용
문서만으로는 실제 한글 뷰어가 어느 필드를 렌더링에 반영하는지까지는 확증
불가 — 잔여 리스크로 아래에 문서화.

### 2. sparse 병합 표 왕복
2행×2열 표에서 `(0,0)`을 `rowSpan=2`로 세로 병합(`(1,0)`은 실제 셀,
`(0,1)`은 covered라 tc 자체를 안 만듦, `(1,1)`만 존재)해서 쓴 뒤 재읽기한
결과, 쓴 그대로 정확히 복원됨:
```
tr 0: tc count=2 → (0,0) span(1,2) / (1,0) span(1,1)
tr 1: tc count=1 → (1,1) span(1,1)   (← (0,1)은 애초에 tc가 없음)
```
`SimpleTable.hwpx`(실제 hwpxlib 테스트 픽스처)를 직접 unzip해 확인했던
sparse 표현과 정확히 같은 구조 — `parseTableSpec`의 `reservedUntilRow` 로직을
그대로 이식해 쓰면 된다는 계획을 확정.

### 3. 정렬 왕복 + `linesegarray` 생략 안전성
`ParaPr.align().horizontal(CENTER)`로 쓴 문단이 재읽기 시 정확히
`align=CENTER`로 복원됨. 이번 스파이크의 모든 신규 문단(A/B/C/D 문단 4개 +
표 안 셀 문단 3개, 총 7개)이 `createLineSegArray()`를 한 번도 호출하지
않았는데도 `HWPXReader`가 크래시·경고 없이 전부 정상 파싱·텍스트 추출
성공 — `MakeTabHwpx.java`가 보여준 낙관적 패턴이 표·서식이 섞인 문서
전체에서도 그대로 유지됨을 재확인.

## 잔여 리스크 (정직하게 문서화)
- **뷰어 렌더링 확증 불가**: 위 3가지는 전부 hwpxlib 자신의 write→read
  왕복 검증이다. 실제 한글/한워드가 `ParaPr.breakSetting().pageBreakBefore()`
  ·`ParaPr.align()`·sparse 병합 표를 화면에 어떻게 그리는지는 이 macOS
  개발 환경에 뷰어가 없어 확인 불가 — DEC-018/039와 동일한 근본적 제약.
  Windows 실사용자 테스트로 이월, 문서(README/DEC)에 한계로 명시할 것.
- `linesegarray` 생략의 안전성은 hwpxlib 자체 판정(교환 포맷 관례상
  낙관적) 이상은 이번 스파이크로도 못 얻음 — 뷰어 확증과 같은 제약.

## 산출물
- `SpikeWrite.java` — 쪽 나눔 2후보·정렬·sparse 병합 표 write→read 검증
- `output/spike_write.hwpx` — 검증에 사용한 실제 산출물(한컴오피스/
  한컴독스에서 육안 확인 권장)

## 실행 방법
```bash
cd spike/hwpxlib
javac -encoding UTF-8 -cp libs/hwpxlib-main -d out SpikeWrite.java
java -cp "out:libs/hwpxlib-main" SpikeWrite output/spike_write.hwpx
```
