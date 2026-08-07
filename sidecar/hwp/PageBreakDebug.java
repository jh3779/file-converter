import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.HWPCharNormal;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.reader.HWPReader;

/**
 * 테스트 전용 디버그 도구(LineSegDebug·MakeFormattedHwp와 같은 원칙,
 * DEC-018/DEC-027) — 배포용 엔진 번들(engine/hwp)에는 포함하지 않는다.
 *
 * DEC-039 회귀 테스트용: 문단별 pageBreakBefore(ParaShapeProperty1의 19bit,
 * "문단 앞에서 항상 쪽 나눔")를 그대로 노출한다 — HwpToText/HwpToJson 둘 다
 * 이 속성을 안 다뤄서(문서 텍스트·표 구조만 봄) 이 구조를 직접 열람하는
 * 별도 도구가 필요하다.
 *
 * 사용: java PageBreakDebug <in.hwp>
 * 출력(문단별 한 줄, 탭 구분): <문단 인덱스>\t<pageBreakBefore>\t<문단 텍스트>
 */
public class PageBreakDebug {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        for (Section sec : hwp.getBodyText().getSectionList()) {
            for (int i = 0; i < sec.getParagraphCount(); i++) {
                Paragraph p = sec.getParagraph(i);
                int shapeId = p.getHeader().getParaShapeId();
                ParaShape shape = hwp.getDocInfo().getParaShapeList().get(shapeId);
                boolean pageBreakBefore = shape.getProperty1().isSplitPageBeforePara();
                StringBuilder text = new StringBuilder();
                if (p.getText() != null) {
                    for (Object ch : p.getText().getCharList()) {
                        if (ch instanceof HWPCharNormal) {
                            text.append(((HWPCharNormal) ch).getCh());
                        }
                    }
                }
                System.out.println(i + "\t" + pageBreakBefore + "\t" + text);
            }
        }
    }
}
