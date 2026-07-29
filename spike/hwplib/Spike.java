import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.control.Control;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractOption;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractor;
import kr.dogfoot.hwplib.writer.HWPWriter;

import java.io.File;

public class Spike {
    public static void main(String[] args) throws Exception {
        String baseDir = args[0];
        String outDir = args[1];

        String[] targets = {
                "basic/표.hwp",
                "basic/그림.hwp",
                "basic/이미지추가.hwp",
                "basic/머리글꼬리글.hwp",
                "basic/문단번호 1-10 수준.hwp",
                "basic/수식.hwp",
                "basic/각주미주.hwp",
                "basic/차트.hwp",
                "basic/글상자.hwp",
                "big_file.hwp",
                "merging-cell.hwp",
        };

        System.out.println("=== 1) 읽기 + 텍스트 추출 + 구조 인식 ===");
        int ok = 0, fail = 0;
        for (String name : targets) {
            File f = new File(baseDir, name);
            long t0 = System.currentTimeMillis();
            try {
                HWPFile hwp = HWPReader.fromFile(f.getAbsolutePath());
                long readMs = System.currentTimeMillis() - t0;

                TextExtractOption opt = new TextExtractOption();
                opt.setMethod(TextExtractMethod.InsertControlTextBetweenParagraphText);
                opt.setWithControlChar(false);
                opt.setAppendEndingLF(true);
                String text = TextExtractor.extract(hwp, opt);

                int paraCount = 0, tableCount = 0, gsoCount = 0;
                for (Section sec : hwp.getBodyText().getSectionList()) {
                    paraCount += sec.getParagraphCount();
                    for (int i = 0; i < sec.getParagraphCount(); i++) {
                        Paragraph p = sec.getParagraph(i);
                        if (p.getControlList() == null) continue;
                        for (Control c : p.getControlList()) {
                            if (c.getType() == ControlType.Table) tableCount++;
                            else if (c.getType() == ControlType.Gso) gsoCount++;
                        }
                    }
                }
                int binCount = hwp.getBinData().getEmbeddedBinaryDataList().size();

                String preview = text.replaceAll("\\s+", " ").trim();
                if (preview.length() > 120) preview = preview.substring(0, 120) + "…";

                System.out.printf("[OK] %-35s 읽기 %4dms | 문단 %3d | 표 %d | 개체 %d | 첨부바이너리 %d | 텍스트 %d자%n",
                        name, readMs, paraCount, tableCount, gsoCount, binCount, text.length());
                System.out.println("     추출 미리보기: " + preview);
                ok++;
            } catch (Exception e) {
                System.out.printf("[FAIL] %-35s %s: %s%n", name, e.getClass().getSimpleName(), e.getMessage());
                fail++;
            }
        }
        System.out.printf("%n읽기 결과: 성공 %d / 실패 %d%n%n", ok, fail);

        System.out.println("=== 2) 표 내용 추출 상세 (표.hwp) ===");
        HWPFile tableHwp = HWPReader.fromFile(new File(baseDir, "basic/표.hwp").getAbsolutePath());
        TextExtractOption opt = new TextExtractOption();
        opt.setMethod(TextExtractMethod.InsertControlTextBetweenParagraphText);
        opt.setWithControlChar(false);
        opt.setAppendEndingLF(true);
        System.out.println(TextExtractor.extract(tableHwp, opt));

        System.out.println("=== 3) 쓰기 라운드트립 (읽기 → 저장 → 재읽기 → 텍스트 비교) ===");
        String[] roundTripTargets = {"basic/표.hwp", "basic/그림.hwp", "merging-cell.hwp"};
        for (String name : roundTripTargets) {
            HWPFile src = HWPReader.fromFile(new File(baseDir, name).getAbsolutePath());
            String before = TextExtractor.extract(src, opt);
            File out = new File(outDir, "roundtrip-" + new File(name).getName());
            HWPWriter.toFile(src, out.getAbsolutePath());
            HWPFile re = HWPReader.fromFile(out.getAbsolutePath());
            String after = TextExtractor.extract(re, opt);
            System.out.printf("%-25s 재저장 후 재읽기: %s | 텍스트 동일: %s (%d자)%n",
                    name, "성공", before.equals(after) ? "예" : "아니오", after.length());
        }
    }
}
