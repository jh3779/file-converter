import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem;
import kr.dogfoot.hwplib.reader.HWPReader;

/**
 * 테스트 전용 디버그 도구 — 배포용 엔진 번들(engine/hwp)에는 포함하지 않는다
 * (.github/workflows/build.yml의 "Build HWP engine" javac 목록에는 없음,
 * sidecar/hwp/build.sh의 로컬 개발용 빌드에만 포함).
 *
 * DEC-018 회귀 테스트용: JsonToHwp가 생성한 HWP의 문단별 레이아웃 캐시
 * (LineSegItem)를 그대로 노출한다 — 텍스트 왕복(HwpToText)만으로는 "줄마다
 * 별도 LineSegItem이 생기는지·세로 위치가 문서 전체에서 누적되는지"를 전혀
 * 검증할 수 없어서(TextExtractor는 레이아웃 정보를 안 봄), 이 구조를 직접
 * 열람하는 별도 도구가 필요하다.
 *
 * 사용: java LineSegDebug <in.hwp>
 * 출력(문단별 한 줄, 탭 구분): <문단 인덱스>\t<header.lineAlignCount>\t<LineSegItem 개수>\t<textStart:vpos 콤마구분>
 */
public class LineSegDebug {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        for (Section sec : hwp.getBodyText().getSectionList()) {
            for (int i = 0; i < sec.getParagraphCount(); i++) {
                Paragraph p = sec.getParagraph(i);
                int lineAlignCount = p.getHeader().getLineAlignCount();
                int segCount = (p.getLineSeg() != null) ? p.getLineSeg().getLineSegItemList().size() : 0;
                StringBuilder items = new StringBuilder();
                if (p.getLineSeg() != null) {
                    for (LineSegItem item : p.getLineSeg().getLineSegItemList()) {
                        if (items.length() > 0) items.append(",");
                        items.append(item.getTextStartPosition()).append(":").append(item.getLineVerticalPosition());
                    }
                }
                System.out.println(i + "\t" + lineAlignCount + "\t" + segCount + "\t" + items);
            }
        }
    }
}
