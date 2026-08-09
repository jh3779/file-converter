import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.CtrlHeaderGso;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.HeightCriterion;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.HorzRelTo;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.ObjectNumberSort;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.RelativeArrange;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.TextFlowMethod;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.TextHorzArrange;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.VertRelTo;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.WidthCriterion;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.sectiondefine.TextDirection;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.LineChange;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.TextVerticalAlignment;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.control.table.DivideAtPageBoundary;
import kr.dogfoot.hwplib.object.bodytext.control.table.ListHeaderForCell;
import kr.dogfoot.hwplib.object.bodytext.control.table.Row;
import kr.dogfoot.hwplib.object.bodytext.control.table.Table;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.charshape.ParaCharShape;
import kr.dogfoot.hwplib.object.bodytext.paragraph.header.ParaHeader;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.ParaLineSeg;
import kr.dogfoot.hwplib.object.docinfo.BorderFill;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BackSlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderThickness;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderType;
import kr.dogfoot.hwplib.object.docinfo.borderfill.SlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternFill;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternType;
import kr.dogfoot.hwplib.tool.TableCellMerger;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/**
 * 구조 JSON → HWP 사이드카 (DOCX→HWP 파이프라인의 2단계, HwpToJson의 역방향).
 * 사용: java JsonToHwp <in.blocks.json> <out.hwp>
 * 입력: {"blocks":[{"type":"p","text":"...","pageBreakBefore":bool} |
 *   {"type":"table","rows":[["c1","c2"],...],"pageBreakBefore":bool}]}
 * pageBreakBefore(DEC-039)는 이 블록 앞에서 항상 새 쪽에서 시작하라는
 * 표시다 — pdf_to_hwp가 PDF 페이지 경계를 유지하려고 쓴다(원래는 pdfminer의
 * extract_text()가 페이지 구분 없이 전체를 한 문자열로 뭉개, 여러 페이지의
 * 텍스트가 HWP 안에서 한 페이지처럼 이어 붙어 보이는 버그였다).
 *
 * DEC-017 정정(DEC-028): hwplib에는 표를 처음부터 만드는 도구가 "전혀 없다"고
 * 기록했던 게 이전 조사 누락이었음이 확인됨 — 공식 샘플
 * `src/test/sample/Inserting_Table.java`가 정확히 이 방법을 보여준다.
 * 이 파일의 표 생성 로직은 그 샘플을 병합 없는 단순 N×M 표에 맞게 이식한
 * 것이다(스파이크: spike/hwplib/SpikeTable.java에서 왕복 검증 완료).
 * 셀 병합, 셀 안 서식(굵게 등)은 이번 범위 밖 — 셀 텍스트는 평문 한 문단.
 * **실제 한글/한워드 뷰어에서의 최종 렌더링은 hwplib 자체 왕복 검증으로는
 * 확인할 수 없다**(DEC-018과 동일한 근본적 제약, Mac 개발 환경에는 뷰어가
 * 없음) — Windows 실사용자 테스트 필요.
 */
public class JsonToHwp {
    // 줄바꿈 근사치 — 정확한 폰트 메트릭이 없어 실제 한글 문서 표본에서 역산한 값.
    // segmentWidth=42520은 BlankFileMaker(EmptyParagraphAdder)가 이 문서의 페이지/여백
    // 설정에서 실제로 쓰는 한 줄의 폭(HWP 내부 단위)이라 그대로 재사용한다. charWidth=945는
    // hwplib 샘플 sample_hwp/distribution.hwp의 실제 문단(segmentWidth 48188에서 한 줄에
    // 약 51자)을 역산해 얻은 평균 글자 폭 근사치 — 라틴 문자·구두점이 많이 섞이면 오차가
    // 커질 수 있는 알려진 한계(문서화된 단순화, DEC-017과 같은 원칙).
    private static final int SEGMENT_WIDTH = 42520;
    private static final int CHAR_WIDTH = 945;
    private static final int CHARS_PER_LINE = Math.max(1, SEGMENT_WIDTH / CHAR_WIDTH);
    private static final int LINE_HEIGHT = 1000;
    private static final int TEXT_PART_HEIGHT = 1000;
    private static final int BASELINE_DISTANCE = 850;
    private static final int LINE_SPACE = 600;
    // 줄 간 세로 이동폭 — 정밀한 값이 없어 lineHeight와 동일하게 근사한다.
    private static final int LINE_ADVANCE = LINE_HEIGHT;

    // 표 크기 근사치 — 정확한 페이지/여백 계산 없이 열 개수에 비례해 적당히
    // 잡는다(spike/hwplib/SpikeTable.java에서 검증한 2×2, 셀당 50mm×30mm를
    // 일반화). 표 전체 폭은 일반적인 본문 폭(약 150mm)을 넘지 않게 캡을 둔다.
    private static final double MAX_TABLE_WIDTH_MM = 150.0;
    private static final double MIN_CELL_WIDTH_MM = 20.0;
    private static final double CELL_HEIGHT_MM = 10.0;

    private static HWPFile hwp;
    private static int zOrder = 0;

    public static void main(String[] args) throws Exception {
        String json = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        List<Object> blocks = (List<Object>) ((Map<String, Object>) new JsonReader(json).readValue()).get("blocks");

        // 빈 블록(공백뿐인 문단, 빈 표)은 미리 걸러낸다 — 몇 번째가
        // "문서의 첫 블록"인지(=BlankFileMaker가 이미 만들어 둔 첫 문단을
        // 재사용해야 하는지)를 정확히 판단하기 위해서다.
        List<Object[]> items = new ArrayList<>(); // {"p", text, pageBreakBefore} or {"table", TableSpec, pageBreakBefore}
        for (Object o : blocks) {
            Map<String, Object> block = (Map<String, Object>) o;
            String type = (String) block.get("type");
            boolean pageBreakBefore = Boolean.TRUE.equals(block.get("pageBreakBefore"));
            if ("table".equals(type)) {
                TableSpec spec = parseTableSpec(block);
                if (spec != null) items.add(new Object[]{"table", spec, pageBreakBefore});
            } else {
                String text = (String) block.get("text");
                if (text != null && !text.trim().isEmpty()) items.add(new Object[]{"p", text.trim(), pageBreakBefore});
            }
        }

        hwp = BlankFileMaker.make();
        Section section = hwp.getBodyText().getSectionList().get(0);

        if (items.isEmpty()) {
            // 빈 문서 — BlankFileMaker가 만든 빈 문단 그대로 저장한다.
        } else {
            int vpos = 0;
            for (int i = 0; i < items.size(); i++) {
                boolean isFirst = (i == 0);
                boolean isLast = (i == items.size() - 1);
                String kind = (String) items.get(i)[0];
                // 첫 블록은 이 문서의 시작 자체가 이미 "새 쪽"이라
                // pageBreakBefore를 적용할 대상(앞 문단)이 없다 — 무시.
                boolean pageBreakBefore = !isFirst && (Boolean) items.get(i)[2];
                if ("table".equals(kind)) {
                    TableSpec spec = (TableSpec) items.get(i)[1];
                    Paragraph host = isFirst ? section.getParagraph(0) : section.addNewParagraph();
                    vpos = addTableBlock(section, host, spec, isFirst, isLast, vpos, pageBreakBefore);
                } else {
                    String text = (String) items.get(i)[1];
                    if (isFirst) {
                        Paragraph first = section.getParagraph(0);
                        if (first.getText() == null) first.createText();
                        first.getText().addString(text);
                        // +2: BlankFileMaker가 첫 문단에 이미 넣어 둔 섹션/컬럼정의 확장문자.
                        first.getHeader().setCharacterCount(text.length() + 1 + 2);
                        first.getHeader().setLastInList(isLast);
                        vpos = applyLineSeg(first, text, vpos);
                    } else {
                        vpos = addTextParagraph(section, text, isLast, vpos, pageBreakBefore);
                    }
                }
            }
        }

        HWPWriter.toFile(hwp, args[1]);
    }

    /** 파싱된 표 블록 — 행마다 "그 행에서 처음 등장하는 셀"만 담는다(docx_extract.py와
     * 같은 표현: 세로 병합이 위에서 내려와 차지한 칸은 그 행에 아예 안 실림).
     * 세로 병합이 어떤 행 전체를 덮으면 그 행은 빈 배열(`[]`)로 표현되는데,
     * 그래도 반드시 spec.rows에 그대로 보존해야 한다 — 빈 행을 버리면
     * rows.size()(=rowCount)가 원본 행 수보다 줄어 addTableBlock의
     * reservedUntilRow 추적(행 인덱스 기준)이 어긋나 표 구조가 깨진다
     * (자동 리뷰로 발견). */
    private static class TableSpec {
        List<List<Map<String, Object>>> rows;
        double[] colWidthsMm; // null이면 기존 열 개수 비례 근사치로 대체
    }

    private static TableSpec parseTableSpec(Map<String, Object> block) {
        List<Object> rawRows = (List<Object>) block.get("rows");
        if (rawRows == null || rawRows.isEmpty()) return null;
        TableSpec spec = new TableSpec();
        spec.rows = new ArrayList<>();
        for (Object rowObj : rawRows) {
            List<Object> rawRow = (List<Object>) rowObj;
            List<Map<String, Object>> row = new ArrayList<>();
            for (Object cellObj : rawRow) {
                Map<String, Object> cell = (Map<String, Object>) cellObj;
                String text = String.valueOf(cell.get("text")).replace('\n', ' ');
                Map<String, Object> normalized = new java.util.LinkedHashMap<>();
                normalized.put("text", text);
                normalized.put("colSpan", cell.get("colSpan"));
                normalized.put("rowSpan", cell.get("rowSpan"));
                row.add(normalized);
            }
            spec.rows.add(row);
        }
        if (spec.rows.isEmpty()) return null;

        Object rawWidths = block.get("colWidthsMm");
        if (rawWidths instanceof List) {
            List<Object> widthList = (List<Object>) rawWidths;
            spec.colWidthsMm = new double[widthList.size()];
            for (int i = 0; i < widthList.size(); i++) {
                spec.colWidthsMm[i] = ((Double) widthList.get(i));
            }
        }
        return spec;
    }

    private static int addTextParagraph(Section section, String content, boolean last, int startVpos,
                                         boolean pageBreakBefore) throws Exception {
        Paragraph paragraph = section.addNewParagraph();

        ParaHeader header = paragraph.getHeader();
        header.setLastInList(last);
        header.setCharacterCount(content.length() + 1);
        header.getControlMask().setValue(0);
        header.setParaShapeId(findOrCreateParaShape(pageBreakBefore));
        header.setStyleId((short) 0);
        header.getDivideSort().setValue((short) 0);
        header.setCharShapeCount(1);
        header.setRangeTagCount(0);
        header.setInstanceID(0);
        header.setIsMergedByTrack(0);

        paragraph.createText();
        paragraph.getText().addString(content);

        paragraph.createCharShape();
        ParaCharShape charShape = paragraph.getCharShape();
        charShape.addParaCharShape(0, 0);

        return applyLineSeg(paragraph, content, startVpos);
    }

    /**
     * spec(N×M, 셀 병합·실제 열 너비 지원 — DEC-035)을 host 문단에 앵커된 표
     * 컨트롤로 만든다(spike/hwplib/SpikeTable.java 참고 — hwplib 공식 샘플
     * Inserting_Table.java를 일반화). host가 문서의 첫 문단(BlankFileMaker가
     * 이미 만들어 둔 것)이면 그 문단을 그대로 쓰고, 아니면 새로 만든 빈
     * 문단을 쓴다 — 둘 다 표 앵커용 확장 문자만 담아 텍스트 자체는 비운다.
     *
     * 병합: 먼저 병합 없는 균일한 N×M 그리드(셀 1개당 1행×1열)를 통째로
     * 만든 다음, hwplib의 공식 유틸리티 `TableCellMerger`(공식 샘플
     * Merging_Cell.java에서 확인 — 표 병합 전용 도구가 이미 있었음)로
     * 병합 영역을 하나씩 합친다. 직접 병합 로직을 새로 짜지 않고 라이브러리
     * 도구를 재사용하는 것 — 폭/높이 재계산·잔여 셀 제거·행별 셀 개수
     * 재조정까지 이 도구가 전부 처리해준다.
     */
    private static int addTableBlock(Section section, Paragraph host, TableSpec spec,
                                      boolean hostIsFirstParagraph, boolean last, int startVpos,
                                      boolean pageBreakBefore) throws Exception {
        List<List<Map<String, Object>>> rows = spec.rows;
        int rowCount = rows.size();
        // colCount는 첫 행의 colSpan 합으로 구한다 — docx_extract.py가 만드는
        // 그리드는 항상 모든 행의 (병합 감안) 합이 같으므로(python-docx의
        // table.cell(r,c)가 열 개수만큼 항상 값을 주는 것을 그대로 반영한
        // 결과) 첫 행만 봐도 충분하다.
        int colCount = 0;
        for (Map<String, Object> cell : rows.get(0)) colCount += spanInt(cell, "colSpan");

        if (host.getText() == null) host.createText();
        host.getText().addExtendCharForTable();
        ParaHeader header = host.getHeader();
        if (hostIsFirstParagraph) {
            // +2: BlankFileMaker가 첫 문단에 이미 넣어 둔 섹션/컬럼정의 확장문자.
            header.setCharacterCount(1 + 8 + 2);
        } else {
            header.setCharacterCount(1 + 8);
            header.getControlMask().setValue(0);
            header.setParaShapeId(findOrCreateParaShape(pageBreakBefore));
            header.setStyleId((short) 0);
            header.getDivideSort().setValue((short) 0);
            header.setInstanceID(0);
            header.setIsMergedByTrack(0);
        }
        header.setLastInList(last);
        header.setCharShapeCount(1);
        header.setRangeTagCount(0);
        host.createCharShape();
        host.getCharShape().addParaCharShape(0, 0);
        host.createLineSeg();
        LineSegItem hostSeg = host.getLineSeg().addNewLineSegItem();
        hostSeg.setTextStartPosition(0);
        hostSeg.setLineVerticalPosition(startVpos);
        hostSeg.setLineHeight(LINE_HEIGHT);
        hostSeg.setTextPartHeight(TEXT_PART_HEIGHT);
        hostSeg.setDistanceBaseLineToLineVerticalPosition(BASELINE_DISTANCE);
        hostSeg.setLineSpace(LINE_SPACE);
        hostSeg.setStartPositionFromColumn(0);
        hostSeg.setSegmentWidth(SEGMENT_WIDTH);
        hostSeg.getTag().setValue(393216);
        header.setLineAlignCount(1);

        ControlTable table = (ControlTable) host.addNewControl(ControlType.Table);

        double[] colWidthsMm = resolveColumnWidths(spec.colWidthsMm, colCount);
        double tableWidthMm = 0;
        for (double w : colWidthsMm) tableWidthMm += w;
        double tableHeightMm = CELL_HEIGHT_MM * rowCount;

        CtrlHeaderGso ctrlHeader = table.getHeader();
        ctrlHeader.getProperty().setLikeWord(false);
        ctrlHeader.getProperty().setApplyLineSpace(false);
        ctrlHeader.getProperty().setVertRelTo(VertRelTo.Para);
        ctrlHeader.getProperty().setVertRelativeArrange(RelativeArrange.TopOrLeft);
        ctrlHeader.getProperty().setHorzRelTo(HorzRelTo.Para);
        ctrlHeader.getProperty().setHorzRelativeArrange(RelativeArrange.TopOrLeft);
        ctrlHeader.getProperty().setVertRelToParaLimit(false);
        ctrlHeader.getProperty().setAllowOverlap(false);
        ctrlHeader.getProperty().setWidthCriterion(WidthCriterion.Absolute);
        ctrlHeader.getProperty().setHeightCriterion(HeightCriterion.Absolute);
        ctrlHeader.getProperty().setProtectSize(false);
        ctrlHeader.getProperty().setTextFlowMethod(TextFlowMethod.FitWithText);
        ctrlHeader.getProperty().setTextHorzArrange(TextHorzArrange.BothSides);
        ctrlHeader.getProperty().setObjectNumberSort(ObjectNumberSort.Table);
        ctrlHeader.setxOffset(mmToHwp(0.0));
        ctrlHeader.setyOffset(mmToHwp(0.0));
        ctrlHeader.setWidth(mmToHwp(tableWidthMm));
        ctrlHeader.setHeight(mmToHwp(tableHeightMm));
        ctrlHeader.setzOrder(zOrder++);
        ctrlHeader.setOutterMarginLeft(0);
        ctrlHeader.setOutterMarginRight(0);
        ctrlHeader.setOutterMarginTop(0);
        ctrlHeader.setOutterMarginBottom(0);

        Table tableRecord = table.getTable();
        tableRecord.getProperty().setDivideAtPageBoundary(DivideAtPageBoundary.DivideByCell);
        tableRecord.getProperty().setAutoRepeatTitleRow(false);
        tableRecord.setRowCount(rowCount);
        tableRecord.setColumnCount(colCount);
        tableRecord.setCellSpacing(0);
        tableRecord.setLeftInnerMargin(0);
        tableRecord.setRightInnerMargin(0);
        tableRecord.setTopInnerMargin(0);
        tableRecord.setBottomInnerMargin(0);
        tableRecord.setBorderFillId(newBorderFill(false));
        for (int r = 0; r < rowCount; r++) tableRecord.getCellCountOfRowList().add(colCount);

        // 1단계: 병합 없는 균일한 rowCount×colCount 그리드를 통째로 만든다.
        // 각 그리드 칸의 텍스트는 grid[r][c]에 미리 채워 둔다 — 병합 마스터
        // 칸(각 병합 영역의 왼쪽 위)만 실제 텍스트를 받고, 나머지(오른쪽·
        // 아래로 병합에 덮이는 칸)는 빈 문자열로 채운 뒤 2단계에서 제거된다.
        String[][] grid = new String[rowCount][colCount];
        for (String[] r : grid) Arrays.fill(r, "");
        // merges: {row, col, rowSpan, colSpan} — TableCellMerger.mergeCell 인자 순서 그대로.
        List<int[]> merges = new ArrayList<>();
        // 세로 병합이 위에서 내려와 점유한 칸을 추적 — reservedUntilRow[c]는
        // 그 열이 병합으로 점유된 마지막 행 인덱스(포함), 아직 없으면 -1.
        int[] reservedUntilRow = new int[colCount];
        Arrays.fill(reservedUntilRow, -1);

        for (int r = 0; r < rowCount; r++) {
            List<Map<String, Object>> rowCells = rows.get(r);
            int col = 0, cellIdx = 0;
            while (col < colCount) {
                if (reservedUntilRow[col] >= r) {
                    col++;
                    continue;
                }
                Map<String, Object> cellSpec = rowCells.get(cellIdx++);
                int colSpan = spanInt(cellSpec, "colSpan");
                int rowSpan = spanInt(cellSpec, "rowSpan");
                grid[r][col] = (String) cellSpec.get("text");
                if (colSpan > 1 || rowSpan > 1) {
                    merges.add(new int[]{r, col, rowSpan, colSpan});
                }
                if (rowSpan > 1) {
                    for (int cc = col; cc < col + colSpan; cc++) reservedUntilRow[cc] = r + rowSpan - 1;
                }
                col += colSpan;
            }
        }

        int cellBorderFillId = newBorderFill(true);
        for (int r = 0; r < rowCount; r++) {
            Row row = table.addNewRow();
            for (int c = 0; c < colCount; c++) {
                Cell cell = row.addNewCell();
                setListHeaderForCell(cell, c, r, cellBorderFillId, colWidthsMm[c]);
                setParagraphForCell(cell, grid[r][c]);
            }
        }

        // 2단계: 병합 영역을 하나씩 합친다(TableCellMerger가 폭/높이 재계산·
        // 잔여 셀 제거·행별 셀 개수 재조정까지 처리). 균일한 그리드에서
        // 시작했으므로 이 병합은 항상 성공해야 정상 — 그래도 hwplib 내부
        // 유효성 검사(possible())가 실패를 보고하면 그 병합만 건너뛰고
        // 텍스트는 원래 1×1 칸에 그대로 남긴다(텍스트 보존 최우선 원칙).
        for (int[] m : merges) {
            TableCellMerger.mergeCell(table, m[0], m[1], m[2], m[3]);
        }

        return startVpos + LINE_ADVANCE;
    }

    private static int spanInt(Map<String, Object> cellSpec, String key) {
        Object v = cellSpec.get(key);
        return v == null ? 1 : ((Double) v).intValue();
    }

    /** 실제 DOCX 열 너비가 있으면(합이 표 전체 폭 상한을 넘으면 비율 유지한
     * 채 축소해) 그대로 쓰고, 없으면 기존 열 개수 비례 근사치로 대체한다. */
    private static double[] resolveColumnWidths(double[] provided, int colCount) {
        if (provided != null && provided.length == colCount) {
            double total = 0;
            for (double w : provided) total += w;
            if (total > MAX_TABLE_WIDTH_MM) {
                double scale = MAX_TABLE_WIDTH_MM / total;
                double[] scaled = new double[colCount];
                for (int i = 0; i < colCount; i++) scaled[i] = provided[i] * scale;
                return scaled;
            }
            return provided;
        }
        double cellWidthMm = Math.max(MIN_CELL_WIDTH_MM, MAX_TABLE_WIDTH_MM / colCount);
        double[] uniform = new double[colCount];
        Arrays.fill(uniform, cellWidthMm);
        return uniform;
    }

    // pageBreakBefore=false → 기본 ParaShape(id=3, BlankFileMaker가 만든 본문
    // 스타일) 그대로 재사용. true인 경우만 findOrCreateCharShape(DEC-038)과
    // 같은 원칙으로 그 ParaShape을 복제해 "문단 앞에서 항상 쪽 나눔"
    // (ParaShapeProperty1 19bit, spike/hwplib/SpikePageBreak.java에서 실제
    // write+read 왕복으로 비트가 보존됨을 확인)만 켠 새 ParaShape을 한 번만
    // 만들어 캐시한다(문서 안에 페이지 경계가 여러 개여도 같은 ParaShape을
    // 공유).
    private static Integer pageBreakParaShapeId = null;

    private static int findOrCreateParaShape(boolean pageBreakBefore) {
        if (!pageBreakBefore) return 3;
        if (pageBreakParaShapeId != null) return pageBreakParaShapeId;
        ParaShape base = hwp.getDocInfo().getParaShapeList().get(3);
        ParaShape withBreak = base.clone();
        withBreak.getProperty1().setSplitPageBeforePara(true);
        hwp.getDocInfo().getParaShapeList().add(withBreak);
        pageBreakParaShapeId = hwp.getDocInfo().getParaShapeList().size() - 1;
        return pageBreakParaShapeId;
    }

    private static long mmToHwp(double mm) {
        return (long) (mm * 72000.0f / 254.0f + 0.5f);
    }

    /** 표 테두리(outer=true면 테두리 없음, false면 셀 실선) BorderFill을 새로 등록하고 ID를 반환한다. */
    private static int newBorderFill(boolean cellBorder) throws Exception {
        BorderFill bf = hwp.getDocInfo().addNewBorderFill();
        bf.getProperty().set3DEffect(false);
        bf.getProperty().setShadowEffect(false);
        bf.getProperty().setSlashDiagonalShape(SlashDiagonalShape.None);
        bf.getProperty().setBackSlashDiagonalShape(BackSlashDiagonalShape.None);
        BorderType type = cellBorder ? BorderType.Solid : BorderType.None;
        bf.getLeftBorder().setType(type);
        bf.getLeftBorder().setThickness(BorderThickness.MM0_5);
        bf.getLeftBorder().getColor().setValue(0x0);
        bf.getRightBorder().setType(type);
        bf.getRightBorder().setThickness(BorderThickness.MM0_5);
        bf.getRightBorder().getColor().setValue(0x0);
        bf.getTopBorder().setType(type);
        bf.getTopBorder().setThickness(BorderThickness.MM0_5);
        bf.getTopBorder().getColor().setValue(0x0);
        bf.getBottomBorder().setType(type);
        bf.getBottomBorder().setThickness(BorderThickness.MM0_5);
        bf.getBottomBorder().getColor().setValue(0x0);
        bf.getDiagonalBorder().setType(BorderType.None);
        bf.getDiagonalBorder().setThickness(BorderThickness.MM0_5);
        bf.getDiagonalBorder().getColor().setValue(0x0);

        bf.getFillInfo().getType().setPatternFill(true);
        bf.getFillInfo().createPatternFill();
        PatternFill pf = bf.getFillInfo().getPatternFill();
        pf.setPatternType(PatternType.None);
        pf.getBackColor().setValue(-1);
        pf.getPatternColor().setValue(0);

        return hwp.getDocInfo().getBorderFillList().size();
    }

    private static void setListHeaderForCell(Cell cell, int colIndex, int rowIndex, int borderFillId, double widthMm) {
        ListHeaderForCell lh = cell.getListHeader();
        lh.setParaCount(1);
        lh.getProperty().setTextDirection(TextDirection.Horizontal);
        lh.getProperty().setLineChange(LineChange.Normal);
        lh.getProperty().setTextVerticalAlignment(TextVerticalAlignment.Center);
        lh.getProperty().setProtectCell(false);
        lh.getProperty().setEditableAtFormMode(false);
        lh.setColIndex(colIndex);
        lh.setRowIndex(rowIndex);
        lh.setColSpan(1);
        lh.setRowSpan(1);
        lh.setWidth(mmToHwp(widthMm));
        lh.setHeight(mmToHwp(CELL_HEIGHT_MM));
        lh.setLeftMargin(0);
        lh.setRightMargin(0);
        lh.setTopMargin(0);
        lh.setBottomMargin(0);
        lh.setBorderFillId(borderFillId);
        lh.setTextWidth(mmToHwp(widthMm));
        lh.setFieldName("");
    }

    private static void setParagraphForCell(Cell cell, String text) throws Exception {
        Paragraph p = cell.getParagraphList().addNewParagraph();
        ParaHeader ph = p.getHeader();
        ph.setLastInList(true);
        ph.setCharacterCount(text.length() + 1);
        ph.setParaShapeId(1);
        ph.setStyleId((short) 1);
        ph.getDivideSort().setDivideSection(false);
        ph.getDivideSort().setDivideMultiColumn(false);
        ph.getDivideSort().setDividePage(false);
        ph.getDivideSort().setDivideColumn(false);
        ph.setCharShapeCount(1);
        ph.setRangeTagCount(0);
        ph.setLineAlignCount(1);
        ph.setInstanceID(0);
        ph.setIsMergedByTrack(0);

        p.createText();
        p.getText().addString(text);

        p.createCharShape();
        p.getCharShape().addParaCharShape(0, 1);

        p.createLineSeg();
        LineSegItem lsi = p.getLineSeg().addNewLineSegItem();
        lsi.setTextStartPosition(0);
        lsi.setLineVerticalPosition(0);
        lsi.setLineHeight((int) (10.0 * 100.0f));
        lsi.setTextPartHeight((int) (10.0 * 100.0f));
        lsi.setDistanceBaseLineToLineVerticalPosition((int) (10.0 * 0.85 * 100.0f));
        lsi.setLineSpace((int) (3.0 * 100.0f));
        lsi.setStartPositionFromColumn(0);
        lsi.setSegmentWidth((int) mmToHwp(50.0));
        lsi.getTag().setFirstSegmentAtLine(true);
        lsi.getTag().setLastSegmentAtLine(true);
    }

    /**
     * 문단 텍스트 길이에 맞춰 줄바꿈을 계산하고, 실제 문서처럼 줄마다 별도
     * LineSegItem을 만든다(줄 세로 위치는 문서 전체에서 누적 — 문단이 이어질
     * 때마다 0으로 리셋되지 않는다). 이전에는 문단 길이와 무관하게 항상
     * LineSegItem 1개만 만들어서, 긴 문단이 실제 뷰어에서 한 줄로 뭉개져
     * 보이는(형태가 깨지는) 원인이었다 — 실제 한글 문서 표본으로 재현·확인 후 수정.
     *
     * @return 다음 문단(또는 줄)이 이어질 세로 위치
     */
    private static int applyLineSeg(Paragraph paragraph, String content, int startVpos) {
        List<String> lines = wrapLines(content);

        paragraph.createLineSeg();
        ParaLineSeg lineSeg = paragraph.getLineSeg();
        int vpos = startVpos;
        int charOffset = 0;
        for (String line : lines) {
            LineSegItem item = lineSeg.addNewLineSegItem();
            item.setTextStartPosition(charOffset);
            item.setLineVerticalPosition(vpos);
            item.setLineHeight(LINE_HEIGHT);
            item.setTextPartHeight(TEXT_PART_HEIGHT);
            item.setDistanceBaseLineToLineVerticalPosition(BASELINE_DISTANCE);
            item.setLineSpace(LINE_SPACE);
            item.setStartPositionFromColumn(0);
            item.setSegmentWidth(SEGMENT_WIDTH);
            item.getTag().setValue(393216);
            charOffset += line.length();
            vpos += LINE_ADVANCE;
        }
        paragraph.getHeader().setLineAlignCount(lines.size());
        return vpos;
    }

    private static List<String> wrapLines(String content) {
        List<String> lines = new ArrayList<>();
        if (content.isEmpty()) {
            lines.add("");
            return lines;
        }
        for (int i = 0; i < content.length(); i += CHARS_PER_LINE) {
            lines.add(content.substring(i, Math.min(content.length(), i + CHARS_PER_LINE)));
        }
        return lines;
    }

    /**
     * 최소 JSON 파서 — 이 사이드카가 받는 입력은 전적으로 우리 Python 코드가
     * 생성한 표준 JSON(문자열/배열/객체/불리언)뿐이므로, 숫자·null 등 이
     * 스키마에 없는 값 타입은 지원하지 않는다(pageBreakBefore를 읽으려고
     * true/false만 DEC-039에서 추가).
     */
    private static class JsonReader {
        private final String s;
        private int pos = 0;

        JsonReader(String s) {
            this.s = s;
        }

        Object readValue() {
            skipWs();
            char c = s.charAt(pos);
            if (c == '{') return readObject();
            if (c == '[') return readArray();
            if (c == '"') return readString();
            if (c == 't') { expectLiteral("true"); return Boolean.TRUE; }
            if (c == 'f') { expectLiteral("false"); return Boolean.FALSE; }
            if (c == '-' || (c >= '0' && c <= '9')) return readNumber();
            throw new RuntimeException("지원하지 않는 JSON 값 (pos=" + pos + ")");
        }

        void expectLiteral(String literal) {
            if (!s.regionMatches(pos, literal, 0, literal.length())) {
                throw new RuntimeException("예상치 못한 리터럴 (pos=" + pos + ", 예상='" + literal + "')");
            }
            pos += literal.length();
        }

        /** 정수·소수 리터럴을 Double로 반환한다(colSpan/rowSpan/colWidthsMm 전용
         * — 이 스키마가 필요로 하는 숫자는 그 정도뿐이라 별도 Long 분기는 두지 않는다). */
        Double readNumber() {
            int start = pos;
            if (s.charAt(pos) == '-') pos++;
            while (pos < s.length() && Character.isDigit(s.charAt(pos))) pos++;
            if (pos < s.length() && s.charAt(pos) == '.') {
                pos++;
                while (pos < s.length() && Character.isDigit(s.charAt(pos))) pos++;
            }
            return Double.parseDouble(s.substring(start, pos));
        }

        Map<String, Object> readObject() {
            Map<String, Object> map = new java.util.LinkedHashMap<>();
            expect('{');
            skipWs();
            if (peek() == '}') {
                pos++;
                return map;
            }
            while (true) {
                skipWs();
                String key = readString();
                skipWs();
                expect(':');
                Object value = readValue();
                map.put(key, value);
                skipWs();
                char c = s.charAt(pos++);
                if (c == '}') break;
                if (c != ',') throw new RuntimeException("JSON 객체 파싱 오류 (pos=" + pos + ")");
            }
            return map;
        }

        List<Object> readArray() {
            List<Object> list = new ArrayList<>();
            expect('[');
            skipWs();
            if (peek() == ']') {
                pos++;
                return list;
            }
            while (true) {
                list.add(readValue());
                skipWs();
                char c = s.charAt(pos++);
                if (c == ']') break;
                if (c != ',') throw new RuntimeException("JSON 배열 파싱 오류 (pos=" + pos + ")");
                skipWs();
            }
            return list;
        }

        String readString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                char c = s.charAt(pos++);
                if (c == '"') break;
                if (c == '\\') {
                    char esc = s.charAt(pos++);
                    switch (esc) {
                        case '"': sb.append('"'); break;
                        case '\\': sb.append('\\'); break;
                        case '/': sb.append('/'); break;
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'u':
                            String hex = s.substring(pos, pos + 4);
                            sb.append((char) Integer.parseInt(hex, 16));
                            pos += 4;
                            break;
                        default:
                            throw new RuntimeException("알 수 없는 이스케이프: \\" + esc);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }

        void expect(char c) {
            skipWs();
            if (s.charAt(pos) != c) throw new RuntimeException("예상치 못한 문자 '" + s.charAt(pos) + "' (pos=" + pos + ", 예상='" + c + "')");
            pos++;
        }

        char peek() {
            return s.charAt(pos);
        }

        void skipWs() {
            while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) pos++;
        }
    }
}
