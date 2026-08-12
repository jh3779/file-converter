import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.ParaPr;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Para;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Run;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.RunItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.TItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NormalText;
import kr.dogfoot.hwpxlib.reader.HWPXReader;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * 테스트 전용 디버그 도구(PageBreakDebug.java와 같은 원칙, DEC-039) —
 * 배포용 엔진 번들(engine-build/hwp)에는 포함하지 않는다.
 *
 * DEC-049 회귀 테스트용: 문단별 pageBreakBefore(ParaPr.breakSetting()
 * .pageBreakBefore())를 그대로 노출한다 — HwpxToJson 정식 스키마는 이
 * 속성을 안 다뤄서(HWP 쪽과 동일한 이유, HwpxToJson.java 클래스 Javadoc
 * 참고) 이 구조를 직접 열람하는 별도 도구가 필요하다.
 *
 * 사용: java PageBreakDebugHwpx <in.hwpx> <out.txt>
 * 출력(문단별 한 줄, 탭 구분): <문단 인덱스>\t<pageBreakBefore>\t<문단 텍스트>
 */
public class PageBreakDebugHwpx {
    public static void main(String[] args) throws Exception {
        HWPXFile hwpx = HWPXReader.fromFilepath(args[0]);
        StringBuilder out = new StringBuilder();
        int i = 0;
        for (SectionXMLFile section : hwpx.sectionXMLFileList().items()) {
            for (Para p : section.paras()) {
                ParaPr pr = resolveParaPr(hwpx, p.paraPrIDRef());
                boolean pageBreakBefore = pr != null && pr.breakSetting() != null
                        && Boolean.TRUE.equals(pr.breakSetting().pageBreakBefore());
                out.append(i).append('\t').append(pageBreakBefore).append('\t').append(firstText(p)).append('\n');
                i++;
            }
        }
        Files.write(Paths.get(args[1]), out.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static ParaPr resolveParaPr(HWPXFile hwpx, String paraPrIDRef) {
        if (paraPrIDRef == null) return null;
        for (ParaPr pr : hwpx.headerXMLFile().refList().paraProperties().items()) {
            if (paraPrIDRef.equals(pr.id())) return pr;
        }
        return null;
    }

    private static String firstText(Para p) {
        StringBuilder sb = new StringBuilder();
        for (int ri = 0; ri < p.countOfRun(); ri++) {
            Run run = p.getRun(ri);
            for (int ii = 0; ii < run.countOfRunItem(); ii++) {
                RunItem item = run.getRunItem(ii);
                if (!(item instanceof T)) continue;
                T t = (T) item;
                if (t.isOnlyText()) {
                    sb.append(t.onlyText());
                    continue;
                }
                if (t.items() == null) continue;
                for (TItem ti : t.items()) {
                    if (ti instanceof NormalText) sb.append(((NormalText) ti).text());
                }
            }
        }
        return sb.toString();
    }
}
