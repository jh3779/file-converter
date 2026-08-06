import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.ControlHeader;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.CtrlHeaderGso;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.header.HeaderFooterApplyPage;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlContainer;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlRectangle;
import kr.dogfoot.hwplib.object.bodytext.control.gso.GsoControlType;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.TextBox;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.control.table.Row;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.charshape.ParaCharShape;
import kr.dogfoot.hwplib.object.bodytext.paragraph.header.ParaHeader;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.ParaLineSeg;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.ParaText;
import kr.dogfoot.hwplib.object.docinfo.BorderFill;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BackSlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderThickness;
import kr.dogfoot.hwplib.object.docinfo.borderfill.BorderType;
import kr.dogfoot.hwplib.object.docinfo.borderfill.SlashDiagonalShape;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternFill;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.PatternType;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

/**
 * 테스트 전용 도구 — 외부 QA 이슈 #43(HwpToJson이 표가 아닌 컨트롤 안의
 * 텍스트를 조용히 놓치던 버그) 회귀 방지용 픽스처를 만든다. 실사용 공공기관
 * 문서(mois-hwpplan.hwp·unikorea-contract.hwp)에서 실제로 확인된 두 가지
 * 중첩 패턴을 그대로 재현한다 — 제3자 문서라 저장소에 커밋하지 않는 대신
 * (research/hwp-coverage/fetch_samples.sh와 같은 원칙) 합성 픽스처로
 * CI에서 네트워크 없이 검증한다. 배포용 engine-build/hwp에는 포함하지
 * 않는다(MakeFormattedHwp.java와 같은 원칙, DEC-018).
 *
 * 만드는 구조:
 *  1) 머리말(Header) 컨트롤 — 문단 1: 평문 "머리말텍스트", 문단 2: 그 안에
 *     또 표(2×1)를 담아 "셀A"/"셀B" — 머리말 안에 표가 중첩된 실사용
 *     패턴(mois-hwpplan.hwp의 결재란 구조) 재현.
 *  2) 묶음 개체(Container) — 사각형(글상자) 2개를 그룹으로 묶고 각각
 *     "그룹A"/"그룹B" 텍스트 — 그룹 중첩 실사용 패턴(unikorea-contract.hwp의
 *     서명란 구조) 재현.
 *
 * 사용: java MakeNestedControlHwp <out.hwp>
 */
public class MakeNestedControlHwp {
    private HWPFile hwpFile;
    private int zOrder = 0;

    public static void main(String[] args) throws Exception {
        MakeNestedControlHwp maker = new MakeNestedControlHwp();
        HWPFile hwp = BlankFileMaker.make();
        maker.hwpFile = hwp;
        maker.makeHeaderWithNestedTable();
        maker.makeContainerWithTwoTextBoxes();
        HWPWriter.toFile(hwp, args[0]);
        System.out.println("OK: " + args[0]);
    }

    private void makeHeaderWithNestedTable() throws Exception {
        Section section = hwpFile.getBodyText().getSectionList().get(0);
        Paragraph hostParagraph = section.getParagraph(0);
        hostParagraph.getText().addExtendCharForHeader();
        hostParagraph.getHeader().setCharacterCount(1 + 8);

        ControlHeader header = (ControlHeader) hostParagraph.addNewControl(ControlType.Header);
        header.getHeader().setApplyPage(HeaderFooterApplyPage.BothPage);
        header.getListHeader().setParaCount(2);

        Paragraph textPara = header.getParagraphList().addNewParagraph();
        setPlainParagraph(textPara, "머리말텍스트");

        Paragraph tableHostPara = header.getParagraphList().addNewParagraph();
        prepareControlHostParagraph(tableHostPara);
        tableHostPara.getText().addExtendCharForTable();
        ControlTable table = (ControlTable) tableHostPara.addNewControl(ControlType.Table);
        setGsoCtrlHeader(table.getHeader());
        table.getTable().getProperty().setAutoRepeatTitleRow(false);
        table.getTable().setRowCount(1);
        table.getTable().setColumnCount(2);
        table.getTable().setBorderFillId(makeSimpleBorderFill());
        table.getTable().getCellCountOfRowList().add(2);
        Row row = table.addNewRow();
        addCell(row, 0, "셀A");
        addCell(row, 1, "셀B");
    }

    private void makeContainerWithTwoTextBoxes() throws Exception {
        Section section = hwpFile.getBodyText().getSectionList().get(0);
        Paragraph hostParagraph = section.addNewParagraph();
        prepareControlHostParagraph(hostParagraph);
        hostParagraph.getText().addExtendCharForGSO();

        ControlContainer container = (ControlContainer) hostParagraph.addNewGsoControl(GsoControlType.Container);
        setGsoCtrlHeader(container.getHeader());

        // ControlContainer.addNewChildControl()은 CtrlHeaderGso를 null로 넘겨
        // 만든다(hwplib 자체 특성 — 자식 헤더는 별도로 채워야 함을 실측으로
        // 확인) — 대신 직접 생성해 addChildControl()로 붙인다.
        ControlRectangle rectA = new ControlRectangle(new CtrlHeaderGso());
        setGsoCtrlHeader(rectA.getHeader());
        addTextBox(rectA, "그룹A");
        container.addChildControl(rectA);

        ControlRectangle rectB = new ControlRectangle(new CtrlHeaderGso());
        setGsoCtrlHeader(rectB.getHeader());
        addTextBox(rectB, "그룹B");
        container.addChildControl(rectB);
    }

    private void addTextBox(ControlRectangle rect, String text) throws Exception {
        rect.createTextBox();
        TextBox tb = rect.getTextBox();
        tb.getListHeader().setParaCount(1);
        Paragraph p = tb.getParagraphList().addNewParagraph();
        setPlainParagraph(p, text);
    }

    /**
     * 새로 추가한(BlankFileMaker가 만들어둔 게 아닌) 문단이 컨트롤 하나만
     * 담을 때(실제 텍스트 없이 확장문자 하나) 필요한 최소 설정. 확장문자
     * 자체(addExtendCharFor...)와 setCharacterCount는 호출부에서 컨트롤
     * 종류에 맞게 직접 처리한다.
     */
    private void prepareControlHostParagraph(Paragraph p) throws Exception {
        ParaHeader ph = p.getHeader();
        ph.setLastInList(true);
        ph.setCharacterCount(1 + 8);
        ph.setParaShapeId(0);
        ph.setStyleId((short) 0);
        ph.setCharShapeCount(1);
        ph.setRangeTagCount(0);
        ph.setLineAlignCount(1);
        ph.setInstanceID(0);
        ph.setIsMergedByTrack(0);

        p.createText();
        p.createCharShape();
        p.getCharShape().addParaCharShape(0, 0);

        p.createLineSeg();
        LineSegItem lsi = p.getLineSeg().addNewLineSegItem();
        lsi.setTextStartPosition(0);
        lsi.setLineVerticalPosition(0);
        lsi.setLineHeight(1000);
        lsi.setTextPartHeight(1000);
        lsi.setDistanceBaseLineToLineVerticalPosition(850);
        lsi.setLineSpace(600);
        lsi.setStartPositionFromColumn(0);
        lsi.setSegmentWidth(42520);
        lsi.getTag().setFirstSegmentAtLine(true);
        lsi.getTag().setLastSegmentAtLine(true);
    }

    private void setGsoCtrlHeader(CtrlHeaderGso ctrlHeader) {
        ctrlHeader.setxOffset(mmToHwp(10.0));
        ctrlHeader.setyOffset(mmToHwp(10.0));
        ctrlHeader.setWidth(mmToHwp(50.0));
        ctrlHeader.setHeight(mmToHwp(20.0));
        ctrlHeader.setzOrder(zOrder++);
    }

    private int makeSimpleBorderFill() {
        BorderFill bf = hwpFile.getDocInfo().addNewBorderFill();
        bf.getProperty().set3DEffect(false);
        bf.getProperty().setShadowEffect(false);
        bf.getProperty().setSlashDiagonalShape(SlashDiagonalShape.None);
        bf.getProperty().setBackSlashDiagonalShape(BackSlashDiagonalShape.None);
        bf.getLeftBorder().setType(BorderType.Solid);
        bf.getLeftBorder().setThickness(BorderThickness.MM0_5);
        bf.getRightBorder().setType(BorderType.Solid);
        bf.getRightBorder().setThickness(BorderThickness.MM0_5);
        bf.getTopBorder().setType(BorderType.Solid);
        bf.getTopBorder().setThickness(BorderThickness.MM0_5);
        bf.getBottomBorder().setType(BorderType.Solid);
        bf.getBottomBorder().setThickness(BorderThickness.MM0_5);
        bf.getDiagonalBorder().setType(BorderType.None);
        bf.getDiagonalBorder().setThickness(BorderThickness.MM0_5);
        bf.getFillInfo().getType().setPatternFill(true);
        bf.getFillInfo().createPatternFill();
        PatternFill pf = bf.getFillInfo().getPatternFill();
        pf.setPatternType(PatternType.None);
        pf.getBackColor().setValue(-1);
        pf.getPatternColor().setValue(0);
        return hwpFile.getDocInfo().getBorderFillList().size();
    }

    private void addCell(Row row, int colIndex, String text) throws Exception {
        Cell cell = row.addNewCell();
        cell.getListHeader().setParaCount(1);
        cell.getListHeader().setColIndex(colIndex);
        cell.getListHeader().setRowIndex(0);
        cell.getListHeader().setColSpan(1);
        cell.getListHeader().setRowSpan(1);
        cell.getListHeader().setWidth(mmToHwp(25.0));
        cell.getListHeader().setHeight(mmToHwp(20.0));
        cell.getListHeader().setBorderFillId(makeSimpleBorderFill());
        Paragraph p = cell.getParagraphList().addNewParagraph();
        setPlainParagraph(p, text);
    }

    private void setPlainParagraph(Paragraph p, String text) throws Exception {
        ParaHeader ph = p.getHeader();
        ph.setLastInList(true);
        ph.setCharacterCount(text.length() + 1);
        ph.setParaShapeId(0);
        ph.setStyleId((short) 0);
        ph.setCharShapeCount(1);
        ph.setRangeTagCount(0);
        ph.setLineAlignCount(1);
        ph.setInstanceID(0);
        ph.setIsMergedByTrack(0);

        p.createText();
        ParaText pt = p.getText();
        pt.addString(text);

        p.createCharShape();
        ParaCharShape pcs = p.getCharShape();
        pcs.addParaCharShape(0, 0);

        p.createLineSeg();
        ParaLineSeg pls = p.getLineSeg();
        LineSegItem lsi = pls.addNewLineSegItem();
        lsi.setTextStartPosition(0);
        lsi.setLineVerticalPosition(0);
        lsi.setLineHeight(1000);
        lsi.setTextPartHeight(1000);
        lsi.setDistanceBaseLineToLineVerticalPosition(850);
        lsi.setLineSpace(600);
        lsi.setStartPositionFromColumn(0);
        lsi.setSegmentWidth(42520);
        lsi.getTag().setFirstSegmentAtLine(true);
        lsi.getTag().setLastSegmentAtLine(true);
    }

    private long mmToHwp(double mm) {
        return (long) (mm * 72000.0f / 254.0f + 0.5f);
    }
}
