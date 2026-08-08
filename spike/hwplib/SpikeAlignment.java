import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.object.docinfo.parashape.Alignment;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

/**
 * QA(d) 조사용 스파이크 — ParaShapeProperty1.setAlignment(Alignment)로
 * 문단별 정렬(왼쪽/가운데/오른쪽/양쪽)이 다른 새 ParaShape을 만들어 걸고,
 * 파일로 쓰고 다시 읽어서 각 문단의 정렬이 정확히 보존되는지 확인한다
 * (SpikePageBreak.java와 같은 방식 — 같은 ParaShapeProperty1 클래스).
 */
public class SpikeAlignment {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = BlankFileMaker.make();
        Section section = hwp.getBodyText().getSectionList().get(0);

        Alignment[] aligns = {Alignment.Left, Alignment.Center, Alignment.Right, Alignment.Justify};
        String[] texts = {"왼쪽 정렬", "가운데 정렬", "오른쪽 정렬", "양쪽 정렬"};

        ParaShape base = hwp.getDocInfo().getParaShapeList().get(3);

        // 첫 문단(왼쪽=기본값 그대로) 재사용
        Paragraph p0 = section.getParagraph(0);
        p0.getText().addString(texts[0]);
        p0.getHeader().setCharacterCount(texts[0].length() + 1 + 2);

        for (int i = 1; i < aligns.length; i++) {
            ParaShape shape = base.clone();
            shape.getProperty1().setAlignment(aligns[i]);
            hwp.getDocInfo().getParaShapeList().add(shape);
            int shapeId = hwp.getDocInfo().getParaShapeList().size() - 1;

            Paragraph p = section.addNewParagraph();
            p.getHeader().setLastInList(i == aligns.length - 1);
            p.getHeader().getControlMask().setValue(0);
            p.getHeader().setParaShapeId(shapeId);
            p.getHeader().setStyleId((short) 0);
            p.getHeader().getDivideSort().setValue((short) 0);
            p.getHeader().setRangeTagCount(0);
            p.getHeader().setInstanceID(0);
            p.getHeader().setIsMergedByTrack(0);
            p.createText();
            p.getText().addString(texts[i]);
            p.getHeader().setCharacterCount(texts[i].length() + 1);
            p.createCharShape();
            p.getCharShape().addParaCharShape(0, 0);
            p.createLineSeg();
            kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem seg = p.getLineSeg().addNewLineSegItem();
            seg.setTextStartPosition(0);
            seg.setLineVerticalPosition(1000 * i);
            seg.setLineHeight(1000);
            seg.setTextPartHeight(1000);
            seg.setDistanceBaseLineToLineVerticalPosition(850);
            seg.setLineSpace(600);
            seg.setStartPositionFromColumn(0);
            seg.setSegmentWidth(42520);
            seg.getTag().setValue(393216);
            p.getHeader().setLineAlignCount(1);
        }

        HWPWriter.toFile(hwp, args[0]);
        System.out.println("wrote " + args[0]);

        HWPFile reread = HWPReader.fromFile(args[0]);
        Section rs = reread.getBodyText().getSectionList().get(0);
        for (int i = 0; i < rs.getParagraphCount(); i++) {
            Paragraph p = rs.getParagraph(i);
            int shapeId = p.getHeader().getParaShapeId();
            ParaShape shape = reread.getDocInfo().getParaShapeList().get(shapeId);
            System.out.println("para " + i + ": paraShapeId=" + shapeId
                    + " alignment=" + shape.getProperty1().getAlignment());
        }
    }
}
