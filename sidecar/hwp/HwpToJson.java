import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.Control;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.control.table.Row;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.reader.HWPReader;

import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * HWP → 구조 JSON 사이드카 (DEC-007: 구조 추출 → DOCX 생성 파이프라인의 1단계).
 * 사용: java HwpToJson <in.hwp> <out.json>
 * 출력: {"blocks":[{"type":"p","text":"..."} | {"type":"table","rows":[["c1","c2"],...]}]}
 */
public class HwpToJson {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        StringBuilder sb = new StringBuilder();
        sb.append("{\"blocks\":[");
        boolean first = true;
        for (Section sec : hwp.getBodyText().getSectionList()) {
            for (int i = 0; i < sec.getParagraphCount(); i++) {
                Paragraph p = sec.getParagraph(i);
                String text = safeText(p);
                if (!text.isEmpty()) {
                    if (!first) sb.append(',');
                    sb.append("{\"type\":\"p\",\"text\":\"").append(esc(text)).append("\"}");
                    first = false;
                }
                if (p.getControlList() == null) continue;
                for (Control c : p.getControlList()) {
                    if (c.getType() != ControlType.Table) continue;
                    if (!first) sb.append(',');
                    sb.append("{\"type\":\"table\",\"rows\":[");
                    ControlTable table = (ControlTable) c;
                    boolean firstRow = true;
                    for (Row row : table.getRowList()) {
                        if (!firstRow) sb.append(',');
                        sb.append('[');
                        boolean firstCell = true;
                        for (Cell cell : row.getCellList()) {
                            if (!firstCell) sb.append(',');
                            StringBuilder cellText = new StringBuilder();
                            for (Paragraph cp : cell.getParagraphList()) {
                                if (cellText.length() > 0) cellText.append('\n');
                                cellText.append(safeText(cp));
                            }
                            sb.append('"').append(esc(cellText.toString())).append('"');
                            firstCell = false;
                        }
                        sb.append(']');
                        firstRow = false;
                    }
                    sb.append("]}");
                    first = false;
                }
            }
        }
        sb.append("]}");
        Files.write(Paths.get(args[1]), sb.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static String safeText(Paragraph p) {
        try {
            String s = p.getNormalString();
            return s == null ? "" : s.trim();
        } catch (Exception e) {
            return "";
        }
    }

    private static String esc(String s) {
        StringBuilder out = new StringBuilder();
        for (char ch : s.toCharArray()) {
            switch (ch) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': break;
                case '\t': out.append("\\t"); break;
                default:
                    if (ch < 0x20) out.append(String.format("\\u%04x", (int) ch));
                    else out.append(ch);
            }
        }
        return out.toString();
    }
}
