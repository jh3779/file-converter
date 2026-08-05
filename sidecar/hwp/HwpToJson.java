import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.Control;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.control.table.Row;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.charshape.CharPositionShapeIdPair;
import kr.dogfoot.hwplib.object.docinfo.CharShape;
import kr.dogfoot.hwplib.object.docinfo.DocInfo;
import kr.dogfoot.hwplib.object.docinfo.charshape.UnderLineSort;
import kr.dogfoot.hwplib.reader.HWPReader;

import java.util.ArrayList;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * HWP → 구조 JSON 사이드카 (DEC-007: 구조 추출 → DOCX 생성 파이프라인의 1단계).
 * 사용: java HwpToJson <in.hwp> <out.json>
 * 출력: {"blocks":[
 *   {"type":"p","runs":[{"text":"...","bold":bool,"italic":bool,"underline":bool,"size":pt,"color":"RRGGBB"}]} |
 *   {"type":"table","rows":[["c1","c2"],...]}
 * ]}
 *
 * 문단의 서식(굵게/기울임/밑줄/크기/색상)은 ParaCharShape(문단 안에서 글자
 * 모양이 바뀌는 위치·글자모양ID 쌍의 목록)을 글자모양ID → DocInfo의
 * CharShape 레코드로 역참조해 얻는다(DEC-025 계열, Phase 3). 표 셀 내용은
 * 여전히 평문으로만 추출한다(표 자체가 DOCX에서는 이미 실제 표로 나가고
 * 있어 셀 서식까지는 이번 phase 범위 밖).
 */
public class HwpToJson {
    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        DocInfo docInfo = hwp.getDocInfo();
        StringBuilder sb = new StringBuilder();
        sb.append("{\"blocks\":[");
        boolean first = true;
        for (Section sec : hwp.getBodyText().getSectionList()) {
            for (int i = 0; i < sec.getParagraphCount(); i++) {
                Paragraph p = sec.getParagraph(i);
                String runsJson = paragraphRunsJson(p, docInfo);
                if (runsJson != null) {
                    if (!first) sb.append(',');
                    sb.append("{\"type\":\"p\",\"runs\":[").append(runsJson).append("]}");
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

    /**
     * 문단을 ParaCharShape 위치 경계로 잘라 서식별 run 목록의 JSON 조각을
     * 만든다. 문단 전체가 비어 있으면(공백/컨트롤 문자만 있으면) null을
     * 반환해 상위에서 문단 블록 자체를 건너뛰게 한다(기존 safeText().isEmpty()
     * 필터와 동일한 동작). 기존 동작과 맞추기 위해 문단 전체 기준으로 앞뒤
     * 공백만 잘라낸다(문단 중간 run 경계의 공백은 그대로 둠).
     */
    private static String paragraphRunsJson(Paragraph p, DocInfo docInfo) {
        if (p.getText() == null) return null;
        int charSize;
        try {
            charSize = p.getText().getCharSize();
        } catch (Exception e) {
            return null;
        }
        if (charSize == 0) return null;

        ArrayList<CharPositionShapeIdPair> pairs = (p.getCharShape() != null)
                ? p.getCharShape().getPositonShapeIdPairList() : null;

        ArrayList<String> texts = new ArrayList<>();
        ArrayList<CharShape> shapes = new ArrayList<>();
        if (pairs == null || pairs.isEmpty()) {
            // 글자모양 정보가 없으면 서식 없는 단일 run으로 취급 — 텍스트
            // 보존이 최우선이라 서식 추출 실패가 텍스트 손실로 이어지면 안 됨.
            String text = safeText(p);
            if (text.isEmpty()) return null;
            texts.add(text);
            shapes.add(null);
        } else {
            for (int i = 0; i < pairs.size(); i++) {
                int start = (int) pairs.get(i).getPosition();
                int end = (i + 1 < pairs.size()) ? (int) pairs.get(i + 1).getPosition() - 1 : charSize - 1;
                if (start > end || start >= charSize) continue;
                end = Math.min(end, charSize - 1);
                String text;
                try {
                    text = p.getText().getNormalString(start, end);
                } catch (Exception e) {
                    continue;
                }
                if (text == null || text.isEmpty()) continue;
                texts.add(text);
                shapes.add(resolveCharShape(docInfo, pairs.get(i).getShapeId()));
            }
        }
        if (texts.isEmpty()) return null;

        // 문단 전체 기준 앞뒤 공백 제거(기존 safeText().trim()과 동일한 최종
        // 결과를 내기 위함) — 첫/끝 run만 다듬고, 그 결과 비어버리면 버린다.
        int lastIdx = texts.size() - 1;
        texts.set(0, stripLeading(texts.get(0)));
        texts.set(lastIdx, stripTrailing(texts.get(lastIdx)));

        StringBuilder out = new StringBuilder();
        boolean firstRun = true;
        for (int i = 0; i < texts.size(); i++) {
            if (texts.get(i).isEmpty()) continue;
            if (!firstRun) out.append(',');
            out.append(runJson(texts.get(i), shapes.get(i)));
            firstRun = false;
        }
        return firstRun ? null : out.toString();
    }

    private static CharShape resolveCharShape(DocInfo docInfo, long shapeId) {
        int id = (int) shapeId;
        if (id < 0 || id >= docInfo.getCharShapeList().size()) return null;
        return docInfo.getCharShapeList().get(id);
    }

    private static String runJson(String text, CharShape cs) {
        boolean bold = false, italic = false, underline = false;
        double sizePt = 10.0;
        String color = "000000";
        if (cs != null) {
            bold = cs.getProperty().isBold();
            italic = cs.getProperty().isItalic();
            underline = cs.getProperty().getUnderLineSort() != UnderLineSort.None;
            // baseSize는 pt*100 단위(예: 1000 = 10pt) — hwplib 기본 CharShape들의
            // 실측값(CharShapeAdder: 기본 1000=10pt, 부제 900=9pt)으로 확인.
            sizePt = cs.getBaseSize() / 100.0;
            int r = cs.getCharColor().getR();
            int g = cs.getCharColor().getG();
            int b = cs.getCharColor().getB();
            color = String.format("%02X%02X%02X", r, g, b);
        }
        return "{\"text\":\"" + esc(text) + "\",\"bold\":" + bold + ",\"italic\":" + italic
                + ",\"underline\":" + underline + ",\"size\":" + sizePt + ",\"color\":\"" + color + "\"}";
    }

    private static String stripLeading(String s) {
        int i = 0;
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        return s.substring(i);
    }

    private static String stripTrailing(String s) {
        int i = s.length();
        while (i > 0 && Character.isWhitespace(s.charAt(i - 1))) i--;
        return s.substring(0, i);
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
