import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractOption;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractor;
import kr.dogfoot.hwplib.writer.HWPWriter;

import java.io.File;

public class SpikeCreate {
    public static void main(String[] args) throws Exception {
        String outDir = args[0];
        String content = "한글 파일 생성 테스트 — hwplib으로 만든 문서입니다. 2026-07-29";

        HWPFile hwp = BlankFileMaker.make();
        Paragraph p = hwp.getBodyText().getSectionList().get(0).getParagraph(0);
        if (p.getText() == null) p.createText();
        p.getText().addString(content);

        File out = new File(outDir, "created-from-scratch.hwp");
        HWPWriter.toFile(hwp, out.getAbsolutePath());

        HWPFile re = HWPReader.fromFile(out.getAbsolutePath());
        TextExtractOption opt = new TextExtractOption();
        opt.setMethod(TextExtractMethod.InsertControlTextBetweenParagraphText);
        opt.setWithControlChar(false);
        opt.setAppendEndingLF(true);
        String text = TextExtractor.extract(re, opt).trim();

        System.out.println("생성 파일: " + out.getAbsolutePath() + " (" + out.length() + " bytes)");
        System.out.println("재읽기 추출: " + text);
        System.out.println("내용 일치: " + (text.equals(content) ? "예" : "아니오"));
    }
}
