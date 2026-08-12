import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.common.ObjectList;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.CenterLineSort;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.HorizontalAlign2;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.LineType2;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.LineWidth;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.SlashType;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.UnderlineType;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.BorderFill;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.CharPr;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.ParaPr;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.HeightRelTo;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.HorzAlign;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.HorzRelTo;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.NumberingType;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.TextFlowSide;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.TextWrapMethod;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.VertAlign;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.VertRelTo;
import kr.dogfoot.hwpxlib.object.content.section_xml.enumtype.WidthRelTo;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Para;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Run;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.Table;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tc;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tr;
import kr.dogfoot.hwpxlib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwpxlib.writer.HWPXWriter;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/**
 * 구조 JSON → HWPX 사이드카 (HWPX Phase 2 쓰기, DEC-049 — DOCX/PDF→HWPX
 * 파이프라인의 2단계, JsonToHwp.java를 hwpxlib API로 이식). 사용:
 * java JsonToHwpx <in.blocks.json> <out.hwpx>
 * 입력 스키마는 JsonToHwp.java와 동일 — docx_extract.py/pdf.py가 포맷
 * 구분 없이 만드는 그대로 재사용한다.
 *
 * hwpxlib의 객체 모델은 hwplib보다 쓰기가 더 단순하다(스파이크로 확인,
 * spike/hwpxlib/RESULT.md "Phase 2(쓰기)" 참고):
 * - Run이 charPrIDRef를 직접 가져서, HWP 쪽에서 필요했던 "문단 안 위치를
 *   가중치로 역산"하는 오프셋 계산이 통째로 불필요하다(DEC-038의 함정
 *   지점 자체가 없음) — run마다 그냥 새 Run을 추가하면 된다.
 * - 병합 표는 hwpxlib 자체가 sparse 표현(덮이는 칸은 Tc 자체가 없음)이라
 *   JsonToHwp.java처럼 "균일한 그리드를 먼저 만들고 TableCellMerger로
 *   합치는" 2단계가 필요 없다 — parseTableSpec의 reservedUntilRow 재구성
 *   로직을 그대로 쓰되, 곧바로 병합된 Tc를 한 번에 쓴다.
 * - linesegarray(글자 위치 캐시)는 생략해도 hwpxlib이 정상 파싱한다
 *   (MakeTabHwpx.java·스파이크 둘 다 확인) — HWP의 LineSegItem 계산
 *   전체가 불필요.
 *
 * **쪽 나눔은 `ParaPr.breakSetting().pageBreakBefore()`를 쓴다**(스파이크로
 * 확정 — 필드 주석이 DEC-039의 hwplib `SplitPageBeforePara`와 정확히
 * 일치, `Para.pageBreak()`라는 이름이 비슷한 대안 필드도 있었지만 의미가
 * 더 모호해 채택 안 함). 이 값은 HwpxToJson.java의 정식 스키마에는 없다
 * (DEC-039와 동일한 원칙 — PageBreakDebugHwpx.java로 별도 검증).
 *
 * **표 셀 병합은 선택이 아니라 필수**다 — 공유 blocks 스키마("한 행에는
 * 그 행에서 처음 등장하는 셀만 담긴다")를 무시하면 열 개수 자체가
 * 깨진다. 문자 서식(DEC-038 대칭)·정렬(DEC-040 대칭)도 함께 반영한다.
 * **표 셀 안 서식·실제 한글/한워드 뷰어에서의 최종 렌더링은 이번 범위
 * 밖**(DEC-018·DEC-028과 동일한 원칙 — Mac 개발 환경에 뷰어가 없어
 * hwpxlib 자체 왕복 검증 이상은 이번 스파이크로도 확증 불가, Windows
 * 실사용자 테스트 필요).
 */
public class JsonToHwpx {
    // 표 크기 근사치 — JsonToHwp.java와 동일한 상수(hwpunit 단위계가
    // hwplib·hwpxlib 둘 다 1/7200인치로 같음을 BlankFileMaker의 페이지
    // 폭(59528 = 210mm)으로 직접 역산해 확인).
    private static final double MAX_TABLE_WIDTH_MM = 150.0;
    private static final double MIN_CELL_WIDTH_MM = 20.0;
    private static final double CELL_HEIGHT_MM = 10.0;

    private static HWPXFile hwpx;
    private static int zOrder = 0;
    private static int nextParaId = 1000;
    private static int nextObjectId = 900000;

    public static void main(String[] args) throws Exception {
        String json = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        List<Object> blocks = (List<Object>) ((Map<String, Object>) new JsonReader(json).readValue()).get("blocks");

        List<Object[]> items = new ArrayList<>(); // {"p", runs, pageBreakBefore, align} or {"table", TableSpec, pageBreakBefore, align}
        for (Object o : blocks) {
            Map<String, Object> block = (Map<String, Object>) o;
            String type = (String) block.get("type");
            boolean pageBreakBefore = Boolean.TRUE.equals(block.get("pageBreakBefore"));
            String align = (String) block.get("align");
            if ("table".equals(type)) {
                TableSpec spec = parseTableSpec(block);
                if (spec != null) items.add(new Object[]{"table", spec, pageBreakBefore, align});
            } else {
                List<Object> rawRuns = (List<Object>) block.get("runs");
                List<Map<String, Object>> runs = normalizeRuns(rawRuns, (String) block.get("text"));
                if (!runs.isEmpty()) items.add(new Object[]{"p", runs, pageBreakBefore, align});
            }
        }

        hwpx = BlankFileMaker.make();
        SectionXMLFile section = hwpx.sectionXMLFileList().get(0);

        if (!items.isEmpty()) {
            for (int i = 0; i < items.size(); i++) {
                boolean isFirst = (i == 0);
                String kind = (String) items.get(i)[0];
                // 첫 블록은 문서 시작 자체가 이미 "새 쪽"이라 pageBreakBefore를
                // 적용할 대상(앞 문단)이 없다 — 무시(JsonToHwp.java와 동일한 원칙).
                boolean pageBreakBefore = !isFirst && (Boolean) items.get(i)[2];
                String align = (String) items.get(i)[3];
                // 첫 블록은 BlankFileMaker가 이미 만들어 둔 첫 문단(SecPr을 담은
                // Run을 포함)을 재사용한다 — HWP와 달리 SecPr은 문단의 문자
                // 스트림이 아닌 별도 Run 필드라 다른 Run을 추가로 붙여도
                // 안전하다(스파이크로 검증한 Run 독립성 그대로).
                Para para = isFirst ? section.getPara(0) : newPara(section);
                para.paraPrIDRefAnd(findOrCreateParaPr(pageBreakBefore, align));
                if ("table".equals(kind)) {
                    addTableToParagraph(para, (TableSpec) items.get(i)[1]);
                } else {
                    addRunsToParagraph(para, (List<Map<String, Object>>) items.get(i)[1]);
                }
            }
        }

        HWPXWriter.toFilepath(hwpx, args[1]);
    }

    private static Para newPara(SectionXMLFile section) {
        Para para = section.addNewPara();
        para.idAnd(String.valueOf(nextParaId++)).paraPrIDRefAnd("3").styleIDRefAnd("0")
                .pageBreakAnd(false).columnBreakAnd(false).merged(false);
        return para;
    }

    /** 파싱된 표 블록 — JsonToHwp.java의 TableSpec과 동일한 표현(행마다
     * "그 행에서 처음 등장하는 셀"만 담고, 세로 병합이 행 전체를 덮으면
     * 빈 배열 `[]`을 그대로 보존해 rows.size()가 원본 행 수와 어긋나지
     * 않게 한다). */
    private static class TableSpec {
        List<List<Map<String, Object>>> rows;
        double[] colWidthsMm;
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

    /** rawRuns(신버전)가 있으면 그대로 쓰고, 없으면 flatText(구버전)를
     * 서식 없는 단일 run으로 감싼다 — JsonToHwp.java의 normalizeRuns와 동일. */
    private static List<Map<String, Object>> normalizeRuns(List<Object> rawRuns, String flatText) {
        List<Map<String, Object>> runs = new ArrayList<>();
        if (rawRuns != null) {
            for (Object o : rawRuns) {
                Map<String, Object> run = (Map<String, Object>) o;
                String text = stringField(run, "text");
                if (text == null || text.isEmpty()) continue;
                runs.add(run);
            }
        } else if (flatText != null && !flatText.trim().isEmpty()) {
            Map<String, Object> run = new java.util.LinkedHashMap<>();
            run.put("text", flatText.trim());
            runs.add(run);
        }
        return runs;
    }

    /** run별로 새 Run을 만들어 문단에 붙인다 — HWP와 달리 문자 위치를
     * 가중치로 역산할 필요가 없다(각 Run이 자기 charPrIDRef를 직접 가짐,
     * 클래스 Javadoc 참고). */
    private static void addRunsToParagraph(Para para, List<Map<String, Object>> runs) {
        for (Map<String, Object> runSpec : runs) {
            String text = stringField(runSpec, "text");
            if (text == null || text.isEmpty()) continue;
            String charPrId = findOrCreateCharPr(
                    boolField(runSpec, "bold"), boolField(runSpec, "italic"), boolField(runSpec, "underline"),
                    doubleField(runSpec, "size"), stringField(runSpec, "color"));
            Run run = para.addNewRun();
            run.charPrIDRef(charPrId);
            run.addNewT().addNewText().textAnd(text);
        }
    }

    // (bold,italic,underline,size,color) 조합 → CharPr id(String). 같은 조합이
    // 반복되면(흔함) 매번 새로 만들지 않고 캐시로 재사용 — JsonToHwp.java의
    // charShapeCache와 동일한 원칙.
    private static final Map<String, String> charPrCache = new java.util.HashMap<>();

    private static String findOrCreateCharPr(boolean bold, boolean italic, boolean underline,
                                              Double sizePt, String colorHex) {
        String key = bold + "|" + italic + "|" + underline + "|" + sizePt + "|" + colorHex;
        String cached = charPrCache.get(key);
        if (cached != null) return cached;
        if (!bold && !italic && !underline && sizePt == null && colorHex == null) {
            charPrCache.put(key, "0");
            return "0"; // 서식 없음 — 기본 글자모양(id 0) 그대로
        }

        CharPr base = hwpx.headerXMLFile().refList().charProperties().get(0);
        CharPr cp = base.clone();
        if (bold) cp.createBold(); else cp.removeBold();
        if (italic) cp.createItalic(); else cp.removeItalic();
        if (underline) {
            cp.createUnderline();
            cp.underline().typeAnd(UnderlineType.BOTTOM);
        } else {
            cp.removeUnderline();
        }
        if (sizePt != null) cp.heightAnd((int) Math.round(sizePt * 100));
        if (colorHex != null && colorHex.matches("[0-9A-Fa-f]{6}")) {
            cp.textColorAnd("#" + colorHex.toUpperCase());
        }
        String id = String.valueOf(hwpx.headerXMLFile().refList().charProperties().count());
        cp.idAnd(id);
        hwpx.headerXMLFile().refList().charProperties().add(cp);
        charPrCache.put(key, id);
        return id;
    }

    // (pageBreakBefore,align) 조합 → ParaPr id(String). 기본 ParaPr(id "3",
    // BlankFileMaker가 만드는 양쪽 정렬)을 복제해 필요한 속성만 켠다 —
    // findOrCreateCharPr과 같은 원칙, JsonToHwp.java의 findOrCreateParaShape과 대칭.
    private static final Map<String, String> paraPrCache = new java.util.HashMap<>();

    private static String findOrCreateParaPr(boolean pageBreakBefore, String align) {
        HorizontalAlign2 alignment = mapAlignment(align);
        if (!pageBreakBefore && alignment == null) return "3";
        String key = pageBreakBefore + "|" + align;
        String cached = paraPrCache.get(key);
        if (cached != null) return cached;
        ParaPr base = hwpx.headerXMLFile().refList().paraProperties().get(3);
        ParaPr pr = base.clone();
        if (pageBreakBefore) {
            pr.createBreakSetting();
            pr.breakSetting().pageBreakBeforeAnd(true);
        }
        if (alignment != null) {
            pr.createAlign();
            pr.align().horizontalAnd(alignment);
        }
        String id = String.valueOf(hwpx.headerXMLFile().refList().paraProperties().count());
        pr.idAnd(id);
        hwpx.headerXMLFile().refList().paraProperties().add(pr);
        paraPrCache.put(key, id);
        return id;
    }

    private static HorizontalAlign2 mapAlignment(String align) {
        if (align == null) return null;
        switch (align) {
            case "left": return HorizontalAlign2.LEFT;
            case "center": return HorizontalAlign2.CENTER;
            case "right": return HorizontalAlign2.RIGHT;
            case "justify": return HorizontalAlign2.JUSTIFY;
            default: return null; // 알 수 없는 값 — 문서 기본 정렬 유지(텍스트 보존 우선)
        }
    }

    private static boolean boolField(Map<String, Object> run, String key) {
        Object v = run.get(key);
        return v != null && (Boolean) v;
    }

    private static Double doubleField(Map<String, Object> run, String key) {
        Object v = run.get(key);
        return v == null ? null : (Double) v;
    }

    private static String stringField(Map<String, Object> run, String key) {
        Object v = run.get(key);
        return v == null ? null : String.valueOf(v);
    }

    /**
     * spec(N×M, 셀 병합·실제 열 너비 지원)을 문단에 새 Run으로 붙는 Table로
     * 만든다. hwpxlib은 병합된 칸을 sparse하게 표현하므로(덮이는 칸은 Tc
     * 자체가 없음, 스파이크로 확인) JsonToHwp.java처럼 균일한 그리드를 먼저
     * 만들고 나중에 합치는 2단계가 필요 없다 — parseTableSpec과 똑같은
     * reservedUntilRow 추적으로 각 행을 훑으며 살아남는 칸만 바로 쓴다.
     */
    private static void addTableToParagraph(Para para, TableSpec spec) {
        List<List<Map<String, Object>>> rows = spec.rows;
        int rowCount = rows.size();
        // colCount는 첫 행의 colSpan 합으로 구한다(JsonToHwp.java와 동일한 근거 —
        // docx_extract.py가 만드는 그리드는 모든 행의 합이 항상 같음).
        int colCount = 0;
        for (Map<String, Object> cell : rows.get(0)) colCount += spanInt(cell, "colSpan");

        double[] colWidthsMm = resolveColumnWidths(spec.colWidthsMm, colCount);
        double tableWidthMm = 0;
        for (double w : colWidthsMm) tableWidthMm += w;
        double tableHeightMm = CELL_HEIGHT_MM * rowCount;

        Run run = para.addNewRun();
        run.charPrIDRef("0");
        Table table = run.addNewTable();
        table.idAnd(String.valueOf(nextObjectId++))
                .zOrderAnd(zOrder++)
                .numberingTypeAnd(NumberingType.TABLE)
                .textWrapAnd(TextWrapMethod.TOP_AND_BOTTOM)
                .textFlowAnd(TextFlowSide.BOTH_SIDES)
                .lockAnd(false)
                .rowCntAnd((short) rowCount)
                .colCntAnd((short) colCount)
                .cellSpacingAnd(0)
                .borderFillIDRefAnd(newBorderFill(false))
                .noAdjustAnd(false);
        table.createSZ();
        table.sz().widthAnd(mmToHwp(tableWidthMm)).widthRelToAnd(WidthRelTo.ABSOLUTE)
                .heightAnd(mmToHwp(tableHeightMm)).heightRelToAnd(HeightRelTo.ABSOLUTE).protectAnd(false);
        table.createPos();
        table.pos().treatAsCharAnd(true).affectLSpacingAnd(false).flowWithTextAnd(true)
                .allowOverlapAnd(false).holdAnchorAndSOAnd(false)
                .vertRelToAnd(VertRelTo.PARA).horzRelToAnd(HorzRelTo.COLUMN)
                .vertAlignAnd(VertAlign.TOP).horzAlignAnd(HorzAlign.LEFT)
                .vertOffsetAnd(0L).horzOffsetAnd(0L);
        table.createInMargin();
        table.inMargin().leftAnd(0L).rightAnd(0L).topAnd(0L).bottomAnd(0L);

        String cellBorderFillId = newBorderFill(true);
        // 세로 병합이 위에서 내려와 점유한 칸을 추적 — JsonToHwp.java의
        // reservedUntilRow와 동일한 알고리즘(다만 grid[][]+merges 목록을
        // 따로 안 두고, 살아남는 칸을 바로 Tc로 쓴다).
        int[] reservedUntilRow = new int[colCount];
        Arrays.fill(reservedUntilRow, -1);
        for (int r = 0; r < rowCount; r++) {
            Tr tr = table.addNewTr();
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
                addCell(tr, col, r, colSpan, rowSpan, (String) cellSpec.get("text"),
                        cellBorderFillId, colWidthsMm[col]);
                if (rowSpan > 1) {
                    for (int cc = col; cc < col + colSpan; cc++) reservedUntilRow[cc] = r + rowSpan - 1;
                }
                col += colSpan;
            }
        }
    }

    private static void addCell(Tr tr, int col, int row, int colSpan, int rowSpan, String text,
                                 String borderFillId, double widthMm) {
        Tc tc = tr.addNewTc();
        tc.nameAnd("").headerAnd(false).hasMarginAnd(false).protectAnd(false)
                .editableAnd(false).dirtyAnd(false).borderFillIDRefAnd(borderFillId);
        tc.createCellAddr();
        tc.cellAddr().colAddrAnd((short) col).rowAddrAnd((short) row);
        tc.createCellSpan();
        tc.cellSpan().colSpanAnd((short) colSpan).rowSpanAnd((short) rowSpan);
        tc.createCellSz();
        tc.cellSz().widthAnd(mmToHwp(widthMm)).heightAnd(mmToHwp(CELL_HEIGHT_MM));
        tc.createCellMargin();
        tc.cellMargin().leftAnd(0L).rightAnd(0L).topAnd(0L).bottomAnd(0L);
        tc.createSubList();
        Para p = tc.subList().addNewPara();
        p.idAnd(String.valueOf(nextParaId++)).paraPrIDRefAnd("3").styleIDRefAnd("0")
                .pageBreakAnd(false).columnBreakAnd(false).merged(false);
        Run r = p.addNewRun();
        r.charPrIDRef("0");
        r.addNewT().addNewText().textAnd(text == null ? "" : text);
    }

    private static int spanInt(Map<String, Object> cellSpec, String key) {
        Object v = cellSpec.get(key);
        return v == null ? 1 : ((Double) v).intValue();
    }

    /** 실제 DOCX 열 너비가 있으면(합이 상한을 넘으면 비율 유지한 채 축소)
     * 그대로 쓰고, 없으면 열 개수 비례 근사치로 대체 — JsonToHwp.java와 동일. */
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

    private static long mmToHwp(double mm) {
        return (long) (mm * 72000.0f / 254.0f + 0.5f);
    }

    /** 표 테두리(outer=true면 셀 실선, false면 테두리 없음 — 인자 이름은
     * JsonToHwp.java의 newBorderFill(cellBorder)과 반대로 안 헷갈리게
     * cellBorder로 통일했다) BorderFill을 새로 등록하고 id를 반환한다.
     * BlankFileMaker가 만드는 기본 BorderFill(id "1","2")은 둘 다 테두리
     * 없음이라 재사용할 수 없다 — id가 "1"부터 시작(0 아님)이라 count()가
     * 아니라 실제 존재하는 id의 최댓값+1로 다음 id를 구한다. */
    private static String newBorderFill(boolean cellBorder) {
        ObjectList<BorderFill> list = hwpx.headerXMLFile().refList().borderFills();
        int maxId = 0;
        for (BorderFill existing : list.items()) {
            try {
                maxId = Math.max(maxId, Integer.parseInt(existing.id()));
            } catch (NumberFormatException ignored) {
                // id가 숫자가 아니면(이 프로젝트가 만든 문서에서는 없음) 무시.
            }
        }
        String id = String.valueOf(maxId + 1);
        BorderFill bf = list.addNew();
        bf.idAnd(id)
                .threeDAnd(false)
                .shadowAnd(false)
                .centerLineAnd(CenterLineSort.NONE)
                .breakCellSeparateLine(false);
        bf.createSlash();
        bf.slash().typeAnd(SlashType.NONE).CrookedAnd(false).isCounter(false);
        bf.createBackSlash();
        bf.backSlash().typeAnd(SlashType.NONE).CrookedAnd(false).isCounter(false);
        LineType2 type = cellBorder ? LineType2.SOLID : LineType2.NONE;
        bf.createLeftBorder();
        bf.leftBorder().typeAnd(type).widthAnd(LineWidth.MM_0_5).color("#000000");
        bf.createRightBorder();
        bf.rightBorder().typeAnd(type).widthAnd(LineWidth.MM_0_5).color("#000000");
        bf.createTopBorder();
        bf.topBorder().typeAnd(type).widthAnd(LineWidth.MM_0_5).color("#000000");
        bf.createBottomBorder();
        bf.bottomBorder().typeAnd(type).widthAnd(LineWidth.MM_0_5).color("#000000");
        bf.createDiagonal();
        bf.diagonal().typeAnd(LineType2.NONE).widthAnd(LineWidth.MM_0_5).color("#000000");
        return id;
    }

    /**
     * 최소 JSON 파서 — JsonToHwp.java의 JsonReader와 동일(사이드카 간 공유
     * 유틸을 두지 않는 기존 관례를 그대로 따름, HwpToJson/HwpxToJson이
     * 이미 독립적인 것과 같은 이유).
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
            if (c == 'n') { expectLiteral("null"); return null; }
            if (c == '-' || (c >= '0' && c <= '9')) return readNumber();
            throw new RuntimeException("지원하지 않는 JSON 값 (pos=" + pos + ")");
        }

        void expectLiteral(String literal) {
            if (!s.regionMatches(pos, literal, 0, literal.length())) {
                throw new RuntimeException("예상치 못한 리터럴 (pos=" + pos + ", 예상='" + literal + "')");
            }
            pos += literal.length();
        }

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
