import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

/**
 * QA (a) 조사용 스파이크 — ParaShapeProperty1.setSplitPageBeforePara(true)로
 * "문단 앞에서 항상 쪽 나눔"을 새 ParaShape에 걸어 특정 문단에만 적용한 뒤,
 * 파일로 쓰고 다시 읽어서 그 비트가 정확히 보존되는지 확인한다.
 */
public class SpikePageBreak {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = BlankFileMaker.make();
        Section section = hwp.getBodyText().getSectionList().get(0);

        // 첫 문단 텍스트
        Paragraph p0 = section.getParagraph(0);
        p0.getText().addString("1페이지 문단");
        p0.getHeader().setCharacterCount("1페이지 문단".length() + 1 + 2);

        // 기본 ParaShape(id=3, addTextParagraph이 쓰는 것과 동일)을 복제해
        // splitPageBeforePara만 켠 새 ParaShape 등록
        ParaShape base = hwp.getDocInfo().getParaShapeList().get(3);
        ParaShape withBreak = base.clone();
        withBreak.getProperty1().setSplitPageBeforePara(true);
        hwp.getDocInfo().getParaShapeList().add(withBreak);
        int breakShapeId = hwp.getDocInfo().getParaShapeList().size() - 1;
        System.out.println("new ParaShape id = " + breakShapeId
                + ", isSplitPageBeforePara(before write) = " + withBreak.getProperty1().isSplitPageBeforePara());

        // 두번째 문단 — 쪽 나눔 적용
        Paragraph p1 = section.addNewParagraph();
        p1.getHeader().setLastInList(true);
        p1.getHeader().getControlMask().setValue(0);
        p1.getHeader().setParaShapeId(breakShapeId);
        p1.getHeader().setStyleId((short) 0);
        p1.getHeader().getDivideSort().setValue((short) 0);
        p1.getHeader().setRangeTagCount(0);
        p1.getHeader().setInstanceID(0);
        p1.getHeader().setIsMergedByTrack(0);
        p1.createText();
        p1.getText().addString("2페이지 문단");
        p1.getHeader().setCharacterCount("2페이지 문단".length() + 1);
        p1.createCharShape();
        p1.getCharShape().addParaCharShape(0, 0);
        p1.createLineSeg();
        kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem seg = p1.getLineSeg().addNewLineSegItem();
        seg.setTextStartPosition(0);
        seg.setLineVerticalPosition(1000);
        seg.setLineHeight(1000);
        seg.setTextPartHeight(1000);
        seg.setDistanceBaseLineToLineVerticalPosition(850);
        seg.setLineSpace(600);
        seg.setStartPositionFromColumn(0);
        seg.setSegmentWidth(42520);
        seg.getTag().setValue(393216);
        p1.getHeader().setLineAlignCount(1);

        HWPWriter.toFile(hwp, args[0]);
        System.out.println("wrote " + args[0]);

        // 재읽기 — 각 문단의 paraShapeId와 그 ParaShape의 splitPageBeforePara 확인
        HWPFile reread = HWPReader.fromFile(args[0]);
        Section rs = reread.getBodyText().getSectionList().get(0);
        for (int i = 0; i < rs.getParagraphCount(); i++) {
            Paragraph p = rs.getParagraph(i);
            int shapeId = p.getHeader().getParaShapeId();
            ParaShape shape = reread.getDocInfo().getParaShapeList().get(shapeId);
            String text = p.getText() != null ? p.getText().toString() : "(no text)";
            System.out.println("para " + i + ": paraShapeId=" + shapeId
                    + " splitPageBeforePara=" + shape.getProperty1().isSplitPageBeforePara()
                    + " text=" + text);
        }
    }
}
