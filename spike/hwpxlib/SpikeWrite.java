import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.HorizontalAlign2;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.ParaPr;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.SubList;
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
import kr.dogfoot.hwpxlib.reader.HWPXReader;
import kr.dogfoot.hwpxlib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwpxlib.writer.HWPXWriter;

/**
 * HWPX Phase 2(쓰기) 착수 전 스파이크 — plan(crystalline-cooking-mist) §0.
 * write→read 왕복으로 3가지 API 불확실성을 직접 확인한다:
 *   1) 쪽 나눔 필드: ParaPr.breakSetting().pageBreakBefore() vs Para.pageBreak()
 *   2) sparse 표현으로 쓴 병합 표(Tc.cellAddr/cellSpan)가 그대로 복원되는지
 *   3) ParaPr.align() 왕복 + linesegarray 생략 시 정상 파싱되는지
 * (MakeTabHwpx.java가 이미 linesegarray 없이 문단을 만들고 있어 낙관적이나,
 * 이번엔 표/서식이 섞인 문서 전체로 재확인한다.)
 */
public class SpikeWrite {
    public static void main(String[] args) throws Exception {
        String outPath = args[0];

        HWPXFile hwpx = BlankFileMaker.make();
        SectionXMLFile sec = hwpx.sectionXMLFileList().get(0);

        // 기존 para 0(BlankFileMaker 기본값)은 그대로 두고 이어서 추가.

        // --- 후보 A: ParaPr.breakSetting().pageBreakBefore() ---
        ParaPr base = hwpx.headerXMLFile().refList().paraProperties().get(3);
        ParaPr pbParaPr = base.clone();
        pbParaPr.createBreakSetting();
        pbParaPr.breakSetting().pageBreakBeforeAnd(true);
        String pbParaPrId = String.valueOf(hwpx.headerXMLFile().refList().paraProperties().count());
        pbParaPr.idAnd(pbParaPrId);
        hwpx.headerXMLFile().refList().paraProperties().add(pbParaPr);
        addTextParagraph(sec, "A-breakSetting", pbParaPrId, false);

        // --- 후보 B: Para.pageBreak (문단 자체 필드), ParaPr은 기본(3) 그대로 ---
        addTextParagraph(sec, "B-para.pageBreak", "3", true);

        // --- 대조군: 둘 다 안 씀 ---
        addTextParagraph(sec, "C-no-break", "3", false);

        // --- 정렬: ParaPr.align().horizontal(CENTER) ---
        ParaPr alignBase = hwpx.headerXMLFile().refList().paraProperties().get(3);
        ParaPr centerParaPr = alignBase.clone();
        centerParaPr.createAlign();
        centerParaPr.align().horizontalAnd(HorizontalAlign2.CENTER);
        String centerParaPrId = String.valueOf(hwpx.headerXMLFile().refList().paraProperties().count());
        centerParaPr.idAnd(centerParaPrId);
        hwpx.headerXMLFile().refList().paraProperties().add(centerParaPr);
        addTextParagraph(sec, "D-center-aligned", centerParaPrId, false);

        // --- 표: 2행 2열, (0,0)이 rowSpan=2로 세로 병합 → 1행에는 tc 2개,
        //     2행에는 covered된 (0,1) 자리를 뺀 tc 1개만 남는 sparse 표현 ---
        addMergedTable(sec);

        HWPXWriter.toFilepath(hwpx, outPath);
        System.out.println("wrote " + outPath);

        // ----- 재읽기 -----
        HWPXFile reread = HWPXReader.fromFilepath(outPath);
        SectionXMLFile rsec = reread.sectionXMLFileList().get(0);
        System.out.println("----- 재읽기: 문단별 pageBreakBefore/pageBreak/align -----");
        for (int i = 0; i < rsec.countOfPara(); i++) {
            Para p = rsec.getPara(i);
            ParaPr pr = reread.headerXMLFile().refList().paraProperties().get(Integer.parseInt(p.paraPrIDRef()));
            String text = firstText(p);
            boolean breakSettingPB = pr.breakSetting() != null
                    && Boolean.TRUE.equals(pr.breakSetting().pageBreakBefore());
            boolean paraPB = Boolean.TRUE.equals(p.pageBreak());
            String align = pr.align() != null ? String.valueOf(pr.align().horizontal()) : "(none)";
            System.out.println("para " + i + " text=" + text
                    + " paraPrIDRef=" + p.paraPrIDRef()
                    + " breakSetting.pageBreakBefore=" + breakSettingPB
                    + " para.pageBreak=" + paraPB
                    + " align=" + align);
        }

        System.out.println("----- 재읽기: 표 구조(sparse 병합 확인) -----");
        Para tablePara = rsec.getPara(rsec.countOfPara() - 1);
        Table table = (Table) tablePara.getRun(0).getRunItem(0);
        System.out.println("rowCnt=" + table.rowCnt() + " colCnt=" + table.colCnt());
        for (int r = 0; r < table.countOfTr(); r++) {
            Tr tr = table.getTr(r);
            System.out.println("tr " + r + ": tc count=" + tr.countOfTc());
            for (int c = 0; c < tr.countOfTc(); c++) {
                Tc tc = tr.getTc(c);
                System.out.println("  tc[" + c + "] cellAddr=(" + tc.cellAddr().colAddr() + ","
                        + tc.cellAddr().rowAddr() + ") cellSpan=(" + tc.cellSpan().colSpan() + ","
                        + tc.cellSpan().rowSpan() + ") text=" + firstText(tc.subList().getPara(0)));
            }
        }
    }

    private static void addTextParagraph(SectionXMLFile sec, String text, String paraPrIDRef, boolean pageBreak) {
        Para para = sec.addNewPara();
        para.idAnd(String.valueOf(1000 + sec.countOfPara()))
                .paraPrIDRefAnd(paraPrIDRef)
                .styleIDRefAnd("0")
                .pageBreakAnd(pageBreak)
                .columnBreakAnd(false)
                .merged(false);
        Run run = para.addNewRun();
        run.charPrIDRef("0");
        run.addNewT().addNewText().textAnd(text);
        // 의도적으로 createLineSegArray() 호출 안 함 — MakeTabHwpx.java와 동일하게
        // linesegarray 없이 만든 문단이 재읽기에서 문제없는지 확인.
    }

    private static void addMergedTable(SectionXMLFile sec) {
        Para para = sec.addNewPara();
        para.idAnd(String.valueOf(2000 + sec.countOfPara()))
                .paraPrIDRefAnd("3")
                .styleIDRefAnd("0")
                .pageBreakAnd(false)
                .columnBreakAnd(false)
                .merged(false);
        Run run = para.addNewRun();
        run.charPrIDRef("0");

        Table table = run.addNewTable();
        table.idAnd("900001")
                .zOrderAnd(0)
                .numberingTypeAnd(NumberingType.TABLE)
                .textWrapAnd(TextWrapMethod.TOP_AND_BOTTOM)
                .textFlowAnd(TextFlowSide.BOTH_SIDES)
                .lockAnd(false)
                .rowCntAnd((short) 2)
                .colCntAnd((short) 2)
                .cellSpacingAnd(0)
                .borderFillIDRefAnd("3")
                .noAdjustAnd(false);
        table.createSZ();
        table.sz().widthAnd(20000L).widthRelToAnd(WidthRelTo.ABSOLUTE)
                .heightAnd(8000L).heightRelToAnd(HeightRelTo.ABSOLUTE).protectAnd(false);
        table.createPos();
        table.pos().treatAsCharAnd(true).affectLSpacingAnd(false).flowWithTextAnd(true)
                .allowOverlapAnd(false).holdAnchorAndSOAnd(false)
                .vertRelToAnd(VertRelTo.PARA).horzRelToAnd(HorzRelTo.COLUMN)
                .vertAlignAnd(VertAlign.TOP).horzAlignAnd(HorzAlign.LEFT)
                .vertOffsetAnd(0L).horzOffsetAnd(0L);
        table.createInMargin();
        table.inMargin().leftAnd(510L).rightAnd(510L).topAnd(141L).bottomAnd(141L);

        // tr0: (0,0) rowSpan=2 세로 병합 + (1,0)
        Tr tr0 = table.addNewTr();
        addCell(tr0, 0, 0, 1, 2, "seed(0,0) rowSpan2");
        addCell(tr0, 1, 0, 1, 1, "seed(1,0)");

        // tr1: (0,1)은 위 병합에 covered → 생략, (1,1)만 존재(sparse)
        Tr tr1 = table.addNewTr();
        addCell(tr1, 1, 1, 1, 1, "seed(1,1)");
    }

    private static void addCell(Tr tr, int col, int row, int colSpan, int rowSpan, String text) {
        Tc tc = tr.addNewTc();
        tc.nameAnd("").headerAnd(false).hasMarginAnd(false).protectAnd(false)
                .editableAnd(false).dirtyAnd(false).borderFillIDRefAnd("3");
        tc.createCellAddr();
        tc.cellAddr().colAddrAnd((short) col).rowAddrAnd((short) row);
        tc.createCellSpan();
        tc.cellSpan().colSpanAnd((short) colSpan).rowSpanAnd((short) rowSpan);
        tc.createCellSz();
        tc.cellSz().widthAnd(10000L).heightAnd(4000L);
        tc.createCellMargin();
        tc.cellMargin().leftAnd(510L).rightAnd(510L).topAnd(141L).bottomAnd(141L);
        tc.createSubList();
        Para p = tc.subList().addNewPara();
        p.idAnd("0").paraPrIDRefAnd("3").styleIDRefAnd("0")
                .pageBreakAnd(false).columnBreakAnd(false).merged(false);
        Run r = p.addNewRun();
        r.charPrIDRef("0");
        r.addNewT().addNewText().textAnd(text);
    }

    private static String firstText(Para p) {
        if (p.countOfRun() == 0) {
            return "(no run)";
        }
        Run run = p.getRun(0);
        if (run.countOfRunItem() == 0) {
            return "(no run item)";
        }
        Object item = run.getRunItem(0);
        if (item instanceof kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T) {
            kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T t =
                    (kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T) item;
            if (t.isOnlyText()) {
                return t.onlyText();
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < t.countOfItems(); i++) {
                Object ti = t.getItem(i);
                if (ti instanceof kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NormalText) {
                    sb.append(((kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NormalText) ti).text());
                }
            }
            return sb.toString();
        }
        return "(non-text run item: " + item.getClass().getSimpleName() + ")";
    }
}
