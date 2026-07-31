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
    // 줄바꿈 근사치 — 정확한 폰트 메트릭이 없어 실제 한글 문서 표본에서 역산한 값.
    // segmentWidth=42520은 BlankFileMaker(EmptyParagraphAdder)가 이 문서의 페이지/여백
    // 설정에서 실제로 쓰는 한 줄의 폭(HWP 내부 단위)이라 그대로 재사용한다. charWidth=945는
    // hwplib 샘플 sample_hwp/distribution.hwp의 실제 문단(segmentWidth 48188에서 한 줄에
    // 약 51자)을 역산해 얻은 평균 글자 폭 근사치 — 라틴 문자·구두점이 많이 섞이면 오차가
    // 커질 수 있는 알려진 한계(문서화된 단순화, DEC-017과 같은 원칙).
    private static final int SEGMENT_WIDTH = 42520;
    private static final int CHAR_WIDTH = 945;
    private static final int CHARS_PER_LINE = Math.max(1, SEGMENT_WIDTH / CHAR_WIDTH);
    private static final int LINE_HEIGHT = 1000;
    private static final int TEXT_PART_HEIGHT = 1000;
    private static final int BASELINE_DISTANCE = 850;
    private static final int LINE_SPACE = 600;
    // 줄 간 세로 이동폭 — 정밀한 값이 없어 lineHeight와 동일하게 근사한다.
    private static final int LINE_ADVANCE = LINE_HEIGHT;

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

            int vpos = applyLineSeg(first, paragraphs.get(0), 0);
            for (int i = 1; i < paragraphs.size(); i++) {
                vpos = addTextParagraph(section, paragraphs.get(i), i == paragraphs.size() - 1, vpos);
            }
        }

        HWPWriter.toFile(hwp, args[1]);
    }

    private static int addTextParagraph(Section section, String content, boolean last, int startVpos) throws Exception {
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
        header.setInstanceID(0);
        header.setIsMergedByTrack(0);

        paragraph.createText();
        paragraph.getText().addString(content);

        paragraph.createCharShape();
        ParaCharShape charShape = paragraph.getCharShape();
        charShape.addParaCharShape(0, 0);

        return applyLineSeg(paragraph, content, startVpos);
    }

    /**
     * 문단 텍스트 길이에 맞춰 줄바꿈을 계산하고, 실제 문서처럼 줄마다 별도
     * LineSegItem을 만든다(줄 세로 위치는 문서 전체에서 누적 — 문단이 이어질
     * 때마다 0으로 리셋되지 않는다). 이전에는 문단 길이와 무관하게 항상
     * LineSegItem 1개만 만들어서, 긴 문단이 실제 뷰어에서 한 줄로 뭉개져
     * 보이는(형태가 깨지는) 원인이었다 — 실제 한글 문서 표본으로 재현·확인 후 수정.
     *
     * @return 다음 문단(또는 줄)이 이어질 세로 위치
     */
    private static int applyLineSeg(Paragraph paragraph, String content, int startVpos) {
        List<String> lines = wrapLines(content);

        paragraph.createLineSeg();
        ParaLineSeg lineSeg = paragraph.getLineSeg();
        int vpos = startVpos;
        int charOffset = 0;
        for (String line : lines) {
            LineSegItem item = lineSeg.addNewLineSegItem();
            item.setTextStartPosition(charOffset);
            item.setLineVerticalPosition(vpos);
            item.setLineHeight(LINE_HEIGHT);
            item.setTextPartHeight(TEXT_PART_HEIGHT);
            item.setDistanceBaseLineToLineVerticalPosition(BASELINE_DISTANCE);
            item.setLineSpace(LINE_SPACE);
            item.setStartPositionFromColumn(0);
            item.setSegmentWidth(SEGMENT_WIDTH);
            item.getTag().setValue(393216);
            charOffset += line.length();
            vpos += LINE_ADVANCE;
        }
        paragraph.getHeader().setLineAlignCount(lines.size());
        return vpos;
    }

    private static List<String> wrapLines(String content) {
        List<String> lines = new ArrayList<>();
        if (content.isEmpty()) {
            lines.add("");
            return lines;
        }
        for (int i = 0; i < content.length(); i += CHARS_PER_LINE) {
            lines.add(content.substring(i, Math.min(content.length(), i + CHARS_PER_LINE)));
        }
        return lines;
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
