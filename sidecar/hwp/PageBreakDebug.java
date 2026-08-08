import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.HWPCharNormal;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.reader.HWPReader;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * 테스트 전용 디버그 도구(LineSegDebug·MakeFormattedHwp와 같은 원칙,
 * DEC-018/DEC-027) — 배포용 엔진 번들(engine/hwp)에는 포함하지 않는다.
 *
 * DEC-039 회귀 테스트용: 문단별 pageBreakBefore(ParaShapeProperty1의 19bit,
 * "문단 앞에서 항상 쪽 나눔")를 그대로 노출한다 — HwpToText/HwpToJson 둘 다
 * 이 속성을 안 다뤄서(문서 텍스트·표 구조만 봄) 이 구조를 직접 열람하는
 * 별도 도구가 필요하다.
 *
 * 사용: java PageBreakDebug <in.hwp> <out.txt>
 * 출력(문단별 한 줄, 탭 구분): <문단 인덱스>\t<pageBreakBefore>\t<문단 텍스트>
 *
 * 결과를 System.out으로 바로 찍지 않고 파일에 UTF-8로 쓰는 이유(다른
 * 사이드카 도구·HwpToText와 같은 패턴): PowerShell이 `&`로 외부 프로세스
 * stdout을 캡처하면 콘솔 코드페이지(Windows CI 기본값은 UTF-8이 아님)로
 * 디코딩해 한글이 깨진다 — 실제로 build-windows에서 이 문제로 DEC-039
 * 스모크 테스트가 오탐 실패했다. bash의 `> file` 리다이렉션은 바이트를
 * 그대로 옮기므로 macOS/Linux에서는 드러나지 않았다.
 */
public class PageBreakDebug {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        StringBuilder out = new StringBuilder();
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
                out.append(i).append('\t').append(pageBreakBefore).append('\t').append(text).append('\n');
            }
        }
        Files.write(Paths.get(args[1]), out.toString().getBytes(StandardCharsets.UTF_8));
    }
}
