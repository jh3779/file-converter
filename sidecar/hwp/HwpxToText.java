import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.reader.HWPXReader;
import kr.dogfoot.hwpxlib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwpxlib.tool.textextractor.TextExtractor;
import kr.dogfoot.hwpxlib.tool.textextractor.TextMarks;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * HWPX → TXT 사이드카(QA(h) Phase 1 — 읽기, 외부 QA 요청). 사용:
 * java HwpxToText <in.hwpx> <out.txt>
 *
 * hwpxlib(Apache-2.0, neolord0 — hwplib과 같은 저자, 순수 JDK로 외부 런타임
 * 의존성 없음)의 내장 TextExtractor를 그대로 쓴다 — HwpToText.java가
 * hwplib의 TextExtractor를 쓰는 것과 같은 원칙.
 */
public class HwpxToText {
    public static void main(String[] args) throws Exception {
        HWPXFile hwpx = HWPXReader.fromFilepath(args[0]);
        String text = TextExtractor.extract(hwpx,
                TextExtractMethod.InsertControlTextBetweenParagraphText,
                true,
                new TextMarks().lineBreakAnd("\n").paraSeparatorAnd("\n"));
        Files.write(Paths.get(args[1]), text.getBytes(StandardCharsets.UTF_8));
    }
}
