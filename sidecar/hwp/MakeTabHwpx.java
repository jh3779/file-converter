import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Para;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Run;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T;
import kr.dogfoot.hwpxlib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwpxlib.writer.HWPXWriter;

/**
 * 테스트 전용 디버그 도구(LineSegDebug·MakeFormattedHwp와 같은 원칙,
 * DEC-018/DEC-027) — 배포용 엔진 번들(engine/hwp)에는 포함하지 않는다.
 *
 * HwpxToJson의 Tab 처리(회귀 수정) 검증용: 문단 하나에 "가나" + Tab + "다라"를
 * 담은 최소 HWPX를 만든다. hwpxlib에는 hwplib의 BlankFileMaker에 대응하는
 * 빈 문서 생성기가 있어 표를 새로 만드는 도구(JsonToHwp의 표 로직)만큼
 * 복잡하지 않다.
 *
 * 사용: java MakeTabHwpx <out.hwpx>
 */
public class MakeTabHwpx {
    public static void main(String[] args) throws Exception {
        HWPXFile hwpx = BlankFileMaker.make();
        SectionXMLFile sec = hwpx.sectionXMLFileList().get(0);
        Para para = sec.addNewPara();
        para.idAnd("999").paraPrIDRefAnd("0").styleIDRefAnd("0")
                .pageBreakAnd(false).columnBreakAnd(false).merged(false);
        Run run = para.addNewRun();
        run.charPrIDRef("0");
        T t = run.addNewT();
        t.addNewText().textAnd("가나");
        t.addNewTab();
        t.addNewText().textAnd("다라");
        HWPXWriter.toFilepath(hwpx, args[0]);
    }
}
