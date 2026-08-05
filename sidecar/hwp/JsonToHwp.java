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
import kr.dogfoot.hwplib.object.docinfo.borderfill.BackSlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderThickness;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderType;
import kr.dogfoot.hwplib.object.docinfo.borderfill.SlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternFill;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternType;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 구조 JSON → HWP 사이드카 (DOCX→HWP 파이프라인의 2단계, HwpToJson의 역방향).
 * 사용: java JsonToHwp <in.blocks.json> <out.hwp>
 * 입력: {"blocks":[{"type":"p","text":"..."} | {"type":"table","rows":[["c1","c2"],...]}]}
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
        List<Object[]> items = new ArrayList<>(); // {"p", text} or {"table", rows}
        for (Object o : blocks) {
            Map<String, Object> block = (Map<String, Object>) o;
            String type = (String) block.get("type");
            if ("table".equals(type)) {
                List<Object> rawRows = (List<Object>) block.get("rows");
                List<List<String>> rows = normalizeRows(rawRows);
                if (!rows.isEmpty()) items.add(new Object[]{"table", rows});
            } else {
                String text = (String) block.get("text");
                if (text != null && !text.trim().isEmpty()) items.add(new Object[]{"p", text.trim()});
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
                if ("table".equals(kind)) {
                    List<List<String>> rows = (List<List<String>>) items.get(i)[1];
                    Paragraph host = isFirst ? section.getParagraph(0) : section.addNewParagraph();
                    vpos = addTableBlock(section, host, rows, isFirst, isLast, vpos);
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
                        vpos = addTextParagraph(section, text, isLast, vpos);
                    }
                }
            }
        }

        HWPWriter.toFile(hwp, args[1]);
    }

    /** 셀 개수를 행마다 맞춘다(짧은 행은 빈 칸으로 채움 — docx_build.py의 표 생성과 같은 원칙). */
    private static List<List<String>> normalizeRows(List<Object> rawRows) {
        List<List<String>> rows = new ArrayList<>();
        if (rawRows == null) return rows;
        int maxCols = 0;
        for (Object rowObj : rawRows) {
            maxCols = Math.max(maxCols, ((List<Object>) rowObj).size());
        }
        if (maxCols == 0) return rows;
        for (Object rowObj : rawRows) {
            List<Object> raw = (List<Object>) rowObj;
            List<String> row = new ArrayList<>();
            for (int c = 0; c < maxCols; c++) {
                String cell = c < raw.size() ? String.valueOf(raw.get(c)) : "";
                row.add(cell.replace('\n', ' '));
            }
            rows.add(row);
        }
        return rows;
    }

    private static int addTextParagraph(Section section, String content, boolean last, int startVpos) throws Exception {
        Paragraph paragraph = section.addNewParagraph();

        ParaHeader header = paragraph.getHeader();
        header.setLastInList(last);
        header.setCharacterCount(content.length() + 1);
        header.getControlMask().setValue(0);
        header.setParaShapeId(3);
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
     * rows(N×M, 셀 병합 없음)를 host 문단에 앵커된 표 컨트롤로 만든다
     * (spike/hwplib/SpikeTable.java 참고 — hwplib 공식 샘플
     * Inserting_Table.java를 일반화). host가 문서의 첫 문단(BlankFileMaker가
     * 이미 만들어 둔 것)이면 그 문단을 그대로 쓰고, 아니면 새로 만든 빈
     * 문단을 쓴다 — 둘 다 표 앵커용 확장 문자만 담아 텍스트 자체는 비운다.
     */
    private static int addTableBlock(Section section, Paragraph host, List<List<String>> rows,
                                      boolean hostIsFirstParagraph, boolean last, int startVpos) throws Exception {
        int rowCount = rows.size();
        int colCount = rows.get(0).size();

        if (host.getText() == null) host.createText();
        host.getText().addExtendCharForTable();
        ParaHeader header = host.getHeader();
        if (hostIsFirstParagraph) {
            // +2: BlankFileMaker가 첫 문단에 이미 넣어 둔 섹션/컬럼정의 확장문자.
            header.setCharacterCount(1 + 8 + 2);
        } else {
            header.setCharacterCount(1 + 8);
            header.getControlMask().setValue(0);
            header.setParaShapeId(3);
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

        double cellWidthMm = Math.max(MIN_CELL_WIDTH_MM, MAX_TABLE_WIDTH_MM / colCount);
        double tableWidthMm = cellWidthMm * colCount;
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

        int cellBorderFillId = newBorderFill(true);
        for (int r = 0; r < rowCount; r++) {
            Row row = table.addNewRow();
            for (int c = 0; c < colCount; c++) {
                Cell cell = row.addNewCell();
                setListHeaderForCell(cell, c, r, cellBorderFillId, cellWidthMm);
                setParagraphForCell(cell, rows.get(r).get(c));
            }
        }

        return startVpos + LINE_ADVANCE;
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
     * 생성한 표준 JSON(문자열/배열/객체)뿐이므로, 숫자·불리언·null 등
     * 이 스키마에 없는 값 타입은 지원하지 않는다.
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
            throw new RuntimeException("지원하지 않는 JSON 값 (pos=" + pos + ")");
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
