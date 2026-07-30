import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.charshape.ParaCharShape;
import kr.dogfoot.hwplib.object.bodytext.paragraph.header.ParaHeader;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.LineSegItem;
import kr.dogfoot.hwplib.object.bodytext.paragraph.lineseg.ParaLineSeg;
import kr.dogfoot.hwplib.tool.blankfilemaker.BlankFileMaker;
import kr.dogfoot.hwplib.writer.HWPWriter;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 구조 JSON → HWP 사이드카 (DOCX→HWP 파이프라인의 2단계, HwpToJson의 역방향).
 * 사용: java JsonToHwp <in.blocks.json> <out.hwp>
 * 입력: {"blocks":[{"type":"p","text":"..."} | {"type":"table","rows":[["c1","c2"],...]}]}
 *
 * hwplib에는 표를 처음부터 새로 만드는 도구가 없다(기존 표를 읽어 그대로
 * 다시 저장하는 라운드트립만 검증됨 — spike/hwplib/RESULT.md). 낮은 신뢰도로
 * 표 컨트롤 객체를 직접 조립하기보다, 표는 각 행을 " | "로 이어붙인 한 줄
 * 텍스트 문단으로 안전하게 표현한다 — 내용은 보존되고, 구조만 단순화된다.
 */
public class JsonToHwp {
    public static void main(String[] args) throws Exception {
        String json = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        List<Object> blocks = (List<Object>) ((Map<String, Object>) new JsonReader(json).readValue()).get("blocks");

        List<String> paragraphs = new ArrayList<>();
        for (Object o : blocks) {
            Map<String, Object> block = (Map<String, Object>) o;
            String type = (String) block.get("type");
            if ("table".equals(type)) {
                List<Object> rows = (List<Object>) block.get("rows");
                if (rows == null) continue;
                for (Object rowObj : rows) {
                    List<Object> row = (List<Object>) rowObj;
                    StringBuilder line = new StringBuilder();
                    for (int i = 0; i < row.size(); i++) {
                        if (i > 0) line.append(" | ");
                        line.append(String.valueOf(row.get(i)).replace('\n', ' '));
                    }
                    String text = line.toString().trim();
                    if (!text.isEmpty()) paragraphs.add(text);
                }
            } else {
                String text = (String) block.get("text");
                if (text != null && !text.trim().isEmpty()) paragraphs.add(text.trim());
            }
        }

        HWPFile hwp = BlankFileMaker.make();
        Section section = hwp.getBodyText().getSectionList().get(0);
        Paragraph first = section.getParagraph(0);

        if (paragraphs.isEmpty()) {
            // 빈 문서 — BlankFileMaker가 만든 빈 문단 그대로 저장한다.
        } else {
            if (first.getText() == null) first.createText();
            first.getText().addString(paragraphs.get(0));
            // +2: BlankFileMaker가 첫 문단에 이미 넣어 둔 섹션/컬럼정의 확장문자.
            first.getHeader().setCharacterCount(paragraphs.get(0).length() + 1 + 2);
            first.getHeader().setLastInList(paragraphs.size() == 1);

            for (int i = 1; i < paragraphs.size(); i++) {
                addTextParagraph(section, paragraphs.get(i), i == paragraphs.size() - 1);
            }
        }

        HWPWriter.toFile(hwp, args[1]);
    }

    private static void addTextParagraph(Section section, String content, boolean last) throws Exception {
        Paragraph paragraph = section.addNewParagraph();

        ParaHeader header = paragraph.getHeader();
        header.setLastInList(last);
        header.setCharacterCount(content.length() + 1);
        header.getControlMask().setValue(0);
        header.setParaShapeId(3);
        header.setStyleId((short) 0);
        header.getDivideSort().setValue((short) 0);
        header.setCharShapeCount(1);
        header.setRangeTagCount(0);
        header.setLineAlignCount(1);
        header.setInstanceID(0);
        header.setIsMergedByTrack(0);

        paragraph.createText();
        paragraph.getText().addString(content);

        paragraph.createCharShape();
        ParaCharShape charShape = paragraph.getCharShape();
        charShape.addParaCharShape(0, 0);

        paragraph.createLineSeg();
        ParaLineSeg lineSeg = paragraph.getLineSeg();
        LineSegItem item = lineSeg.addNewLineSegItem();
        item.setTextStartPosition(0);
        item.setLineVerticalPosition(0);
        item.setLineHeight(1000);
        item.setTextPartHeight(1000);
        item.setDistanceBaseLineToLineVerticalPosition(850);
        item.setLineSpace(600);
        item.setStartPositionFromColumn(0);
        item.setSegmentWidth(42520);
        item.getTag().setValue(393216);
    }

    /**
     * 최소 JSON 파서 — 이 사이드카가 받는 입력은 전적으로 우리 Python 코드가
     * 생성한 표준 JSON(문자열/배열/객체)뿐이므로, 숫자·불리언·null 등
     * 이 스키마에 없는 값 타입은 지원하지 않는다.
     */
    private static class JsonReader {
        private final String s;
        private int pos = 0;

        JsonReader(String s) {
            this.s = s;
        }

        Object readValue() {
            skipWs();
            char c = s.charAt(pos);
            if (c == '{') return readObject();
            if (c == '[') return readArray();
            if (c == '"') return readString();
            throw new RuntimeException("지원하지 않는 JSON 값 (pos=" + pos + ")");
        }

        Map<String, Object> readObject() {
            Map<String, Object> map = new java.util.LinkedHashMap<>();
            expect('{');
            skipWs();
            if (peek() == '}') {
                pos++;
                return map;
            }
            while (true) {
                skipWs();
                String key = readString();
                skipWs();
                expect(':');
                Object value = readValue();
                map.put(key, value);
                skipWs();
                char c = s.charAt(pos++);
                if (c == '}') break;
                if (c != ',') throw new RuntimeException("JSON 객체 파싱 오류 (pos=" + pos + ")");
            }
            return map;
        }

        List<Object> readArray() {
            List<Object> list = new ArrayList<>();
            expect('[');
            skipWs();
            if (peek() == ']') {
                pos++;
                return list;
            }
            while (true) {
                list.add(readValue());
                skipWs();
                char c = s.charAt(pos++);
                if (c == ']') break;
                if (c != ',') throw new RuntimeException("JSON 배열 파싱 오류 (pos=" + pos + ")");
                skipWs();
            }
            return list;
        }

        String readString() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                char c = s.charAt(pos++);
                if (c == '"') break;
                if (c == '\\') {
                    char esc = s.charAt(pos++);
                    switch (esc) {
                        case '"': sb.append('"'); break;
                        case '\\': sb.append('\\'); break;
                        case '/': sb.append('/'); break;
                        case 'n': sb.append('\n'); break;
                        case 'r': sb.append('\r'); break;
                        case 't': sb.append('\t'); break;
                        case 'b': sb.append('\b'); break;
                        case 'f': sb.append('\f'); break;
                        case 'u':
                            String hex = s.substring(pos, pos + 4);
                            sb.append((char) Integer.parseInt(hex, 16));
                            pos += 4;
                            break;
                        default:
                            throw new RuntimeException("알 수 없는 이스케이프: \\" + esc);
                    }
                } else {
                    sb.append(c);
                }
            }
            return sb.toString();
        }

        void expect(char c) {
            skipWs();
            if (s.charAt(pos) != c) throw new RuntimeException("예상치 못한 문자 '" + s.charAt(pos) + "' (pos=" + pos + ", 예상='" + c + "')");
            pos++;
        }

        char peek() {
            return s.charAt(pos);
        }

        void skipWs() {
            while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) pos++;
        }
    }
}
