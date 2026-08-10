import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.reader.HWPXReader;
import kr.dogfoot.hwpxlib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwpxlib.tool.textextractor.TextExtractor;
import kr.dogfoot.hwpxlib.tool.textextractor.TextMarks;

/**
 * QA(h) HWPX 지원 조사용 스파이크 — hwplib 기술 스파이크(spike/hwplib/Spike.java)와
 * 같은 원칙. hwpxlib(Apache-2.0, neolord0 — hwplib과 같은 저자)로 실제 .hwpx
 * 샘플을 읽어 텍스트 추출이 되는지 확인한다.
 */
public class Spike {
    public static void main(String[] args) throws Exception {
        String path = args[0];
        HWPXFile hwpxFile = HWPXReader.fromFilepath(path);
        System.out.println("읽기 성공: " + path);
        System.out.println("섹션 수: " + hwpxFile.sectionXMLFileList().count());

        String text = TextExtractor.extract(hwpxFile,
                TextExtractMethod.InsertControlTextBetweenParagraphText,
                true,
                new TextMarks().lineBreakAnd("\n").paraSeparatorAnd("\n"));
        System.out.println("----- 추출된 텍스트 -----");
        System.out.println(text);
    }
}
