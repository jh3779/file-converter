import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.header.ParaHeader;
import kr.dogfoot.hwplib.object.docinfo.CharShape;
import kr.dogfoot.hwplib.object.docinfo.DocInfo;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

/**
 * 테스트 전용 도구 — HwpToJson의 서식(굵게/기울임/크기/색상) 추출 로직을
 * 검증하기 위한 픽스처 HWP를 만든다. 배포용 engine-build/hwp에는 포함하지
 * 않는다(LineSegDebug.java와 같은 원칙, DEC-018).
 *
 * BlankFileMaker가 만드는 첫 문단(section.getParagraph(0))은 섹션/컬럼
 * 정의용 확장 컨트롤 문자가 이미 들어있어(EmptyParagraphAdder) 텍스트
 * 위치가 0부터 시작하지 않는다 — 여러 run의 위치 경계를 다루는 이 테스트
 * 픽스처에서는 혼란만 커지므로, section.addNewParagraph()로 새로 추가한
 * "깨끗한" 문단에서만 서식을 테스트한다(원 위치 0부터 시작함을 실측 확인).
 *
 * 사용: java MakeFormattedHwp <out.hwp>
 */
public class MakeFormattedHwp {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = BlankFileMaker.make();
        DocInfo docInfo = hwp.getDocInfo();

        CharShape base = docInfo.getCharShapeList().get(0);

        CharShape bold = base.clone();
        bold.getProperty().setBold(true);
        docInfo.getCharShapeList().add(bold);
        int boldId = docInfo.getCharShapeList().size() - 1;

        CharShape italicBigRed = base.clone();
        italicBigRed.getProperty().setItalic(true);
        italicBigRed.setBaseSize(1800); // 18pt
        italicBigRed.getCharColor().setValue(0xFF); // R=255 (Color4Byte: R은 하위 바이트)
        docInfo.getCharShapeList().add(italicBigRed);
        int italicBigRedId = docInfo.getCharShapeList().size() - 1;

        Section section = hwp.getBodyText().getSectionList().get(0);

        String run1 = "일반텍스트";
        String run2 = "굵은텍스트";
        Paragraph mixed = addCleanParagraph(section, run1 + run2, false);
        mixed.getHeader().setCharShapeCount(2);
        mixed.getCharShape().addParaCharShape(0, 0);
        mixed.getCharShape().addParaCharShape(run1.length(), boldId);

        String run3 = "빨간색기울임큰글씨";
        Paragraph italic = addCleanParagraph(section, run3, true);
        italic.getCharShape().addParaCharShape(0, italicBigRedId);

        HWPWriter.toFile(hwp, args[0]);
    }

    private static Paragraph addCleanParagraph(Section section, String content, boolean last) throws Exception {
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
        header.setLineAlignCount(1);

        paragraph.createText();
        paragraph.getText().addString(content);
        paragraph.createCharShape();

        paragraph.createLineSeg();
        kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem item =
                paragraph.getLineSeg().addNewLineSegItem();
        item.setTextStartPosition(0);
        item.setLineVerticalPosition(0);
        item.setLineHeight(1000);
        item.setTextPartHeight(1000);
        item.setDistanceBaseLineToLineVerticalPosition(850);
        item.setLineSpace(600);
        item.setStartPositionFromColumn(0);
        item.setSegmentWidth(42520);
        item.getTag().setValue(393216);

        return paragraph;
    }
}
