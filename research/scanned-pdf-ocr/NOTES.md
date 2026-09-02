# 스캔 PDF(이미지 기반) 지원 검토 — RAG 강의 학습 내용 전달

> 2026-09-02 · 결정 문서 아님 — `docs/06_open_questions.md`에 새 OQ로 등록할지 판단하기 위한
> 참고 자료. 출처는 별도 학습 저장소(LG CNS AI 캠퍼스 RAG 파트)의 "문서 로딩" 실습이며,
> file-converter 코드베이스에서 실제로 구현·검증한 내용은 아직 없다.
>
> 원본 실습(참고용, 이 저장소에는 포함 안 됨):
> `~/Developer/lgcns-ai-campus/practice/rag-part/02-2_문서_로딩_OCR.ipynb`
> `~/Developer/lgcns-ai-campus/practice/rag-part/02-2_문서_로딩_OCR_2_개인실습.ipynb`

## 왜 이 메모가 존재하는가

file-converter의 PDF 텍스트 추출(`app/converters/pdf.py`의 `pdf_to_txt`, 그리고
`pdf_docx.py`·`pdf_pptx.py`가 공유하는 저수준 추출부)은 전부 **pdfminer 기반 텍스트
레이어 추출**이다. PDF 안에 실제 텍스트 객체(`LTTextLine`)가 있을 때만 동작하고,
**스캔한 종이 문서를 이미지로만 담은 PDF(텍스트 레이어 없음)는 지원 범위 밖**이다 —
현재 코드로 그런 PDF를 넣으면 빈 문자열이나 사실상 내용 없는 결과가 나올 것으로
보인다(실제로 스캔 PDF 샘플로 재현 테스트는 아직 안 해봄, 아래 "검증 안 된 것" 참고).

RAG 강의에서 정확히 이 문제("텍스트 레이어가 없거나 부실하면 OCR로 전환")를
다뤘고, 실습 노트북에 이미 이 판단 로직의 최소 구현이 있어 참고할 만하다고 판단해
정리한다.

## RAG 실습에서 다룬 핵심 판단 로직

페이지의 평균 글자 수가 기준치 미만이면 OCR로 전환하는 방식:

```python
def load_pdf_with_ocr(pdf_path, reader, minimum_chars_per_page=20):
    pages = PyPDFLoader(str(pdf_path)).load()
    average_chars = sum(len(p.page_content.strip()) for p in pages) / len(pages)

    if average_chars >= minimum_chars_per_page:
        return {"documents": pages, "mode": "text"}   # 텍스트 레이어 사용

    # 기준 미만 → 페이지를 이미지로 렌더링 후 OCR
    ...
    return {"documents": ocr_documents, "mode": "ocr"}
```

file-converter는 pdfminer를 쓰고 RAG 실습은 `PyPDFLoader`(pypdf)를 쓰지만, 판단
로직 자체(페이지당 평균 글자 수로 텍스트 레이어 유무 판정)는 라이브러리에 무관하게
그대로 옮길 수 있는 아이디어다.

## OCR 엔진별 비교 (실습에서 다룬 3종)

| 엔진 | 실행 방식 | 설치 크기 | 오프라인 데스크톱 적합성 |
|---|---|---|---|
| **Tesseract** | 시스템 실행 파일 + 언어 데이터(`tesseract-ocr`) | 수십 MB(언어팩 포함) | ★★★ — 가장 가벼움. hwplib+JRE 사이드카처럼 별도 실행파일 번들 전례가 이미 있음 |
| **EasyOCR** | PyTorch 런타임 + 모델 다운로드 | 수백 MB(PyTorch 자체가 큼) | ★☆☆ — 설치 크기 부담, macOS는 FFmpeg조차 크기 이유로 번들 안 하는 프로젝트 방침과 상충 |
| **PaddleOCR** | PaddlePaddle 런타임(GPU 빌드는 CUDA 필수) | 수백 MB~GB | ☆☆☆ — GPU 전용 빌드는 애초에 크로스플랫폼 데스크톱 배포와 안 맞음(실습 노트북도 macOS에서 GPU 빌드 설치를 명시적으로 막아둠) |

**결론(가설)**: file-converter처럼 "완전 오프라인 + 크로스플랫폼 단일 설치파일"을
지향하는 프로젝트에는 **Tesseract가 구조적으로 가장 적합**해 보인다. 다만 이건
검증 전 가설이다(아래 참고).

## 레이아웃·표 구조 인식 (참고, 우선순위 낮음)

실습에는 DocLayout-YOLO(문서 영역 탐지: 제목/본문/표 구분)와 Table2HTML(표 이미지
→ HTML 구조 복원)도 있었다. 둘 다 별도 모델 다운로드가 필요하고, file-converter는
이미 pdfminer의 `LTRect`/`LTLine` 조합으로 **텍스트 레이어가 있는 PDF의 표**는
자체적으로 복원하고 있다(DEC-036 등). 이 두 라이브러리는 "스캔된 표"에 한정된
보완재 정도로, OCR 자체보다 우선순위가 낮다고 본다.

## 검증 안 된 것 (중요)

- 실제 스캔 PDF 샘플로 file-converter의 현재 동작을 재현 테스트하지 않았다 —
  "빈 텍스트가 나올 것"은 코드 구조상의 추론이지 실측이 아니다.
- Tesseract를 실제로 file-converter에 번들했을 때의 설치 크기·라이선스(Apache-2.0,
  기존 hwplib과 동일 계열이라 무리 없을 것으로 보이나 미확인)·플랫폼별 배포 방식은
  전혀 검토 안 됨.
- 사용자 수요가 실제로 있는지(스캔 PDF를 변환하려는 사용자가 얼마나 되는지) 확인
  안 됨 — `docs/06_open_questions.md`에 등록한다면 이 부분부터 정리가 필요해 보임.

## 제안

이 메모만으로 결정하지 말고, 필요하다고 판단되면 `docs/06_open_questions.md`에
새 OQ로 등록해 정식 검토 절차(스파이크 → 검증 → DEC)를 밟는 걸 추천한다. 초안
문구 예시:

> **OQ-0XX**: 스캔 PDF(텍스트 레이어 없음) 지원 — 현재 PDF→TXT/DOCX/PPTX는
> pdfminer 텍스트 레이어만 읽어 스캔본은 빈 결과가 나올 것으로 추정(미검증).
> Tesseract OCR 폴백 추가 여부를 검토한다. 후보: Tesseract(가벼움, 시스템 바이너리
> 번들 전례 있음) vs EasyOCR/PaddleOCR(런타임 크고 오프라인 데스크톱에 부적합해
> 보임 — 근거는 `research/scanned-pdf-ocr/NOTES.md`).
