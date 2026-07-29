import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractOption;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractor;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/** HWP → TXT 사이드카. 사용: java HwpToText <in.hwp> <out.txt> */
public class HwpToText {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        TextExtractOption opt = new TextExtractOption();
        opt.setMethod(TextExtractMethod.InsertControlTextBetweenParagraphText);
        opt.setWithControlChar(false);
        opt.setAppendEndingLF(true);
        String text = TextExtractor.extract(hwp, opt);
        Files.write(Paths.get(args[1]), text.getBytes(StandardCharsets.UTF_8));
    }
}
