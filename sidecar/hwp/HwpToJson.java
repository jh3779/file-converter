import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.Control;
import kr.dogfoot.hwplib.object.bodytext.control.ControlEndnote;
import kr.dogfoot.hwplib.object.bodytext.control.ControlFooter;
import kr.dogfoot.hwplib.object.bodytext.control.ControlFootnote;
import kr.dogfoot.hwplib.object.bodytext.control.ControlHeader;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlArc;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlContainer;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlCurve;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlEllipse;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlPolygon;
import kr.dogfoot.hwplib.object.bodytext.control.gso.ControlRectangle;
import kr.dogfoot.hwplib.object.bodytext.control.gso.GsoControl;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.TextBox;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.control.table.Row;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.ParagraphList;
import kr.dogfoot.hwplib.object.bodytext.paragraph.charshape.CharPositionShapeIdPair;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.HWPChar;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.HWPCharNormal;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.HWPCharType;
import kr.dogfoot.hwplib.object.docinfo.CharShape;
import kr.dogfoot.hwplib.object.docinfo.DocInfo;
import kr.dogfoot.hwplib.object.docinfo.ParaShape;
import kr.dogfoot.hwplib.object.docinfo.charshape.UnderLineSort;
import kr.dogfoot.hwplib.object.docinfo.parashape.Alignment;
import kr.dogfoot.hwplib.reader.HWPReader;

import java.util.ArrayList;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * HWP → 구조 JSON 사이드카 (DEC-007: 구조 추출 → DOCX 생성 파이프라인의 1단계).
 * 사용: java HwpToJson <in.hwp> <out.json>
 * 출력: {"blocks":[
 *   {"type":"p","runs":[{"text":"...","bold":bool,"italic":bool,"underline":bool,"size":pt,"color":"RRGGBB"}],
 *     "align":"left"|"center"|"right"|"justify"} |
 *   {"type":"table","rows":[["c1","c2"],...]}
 * ]}
 *
 * 문단의 서식(굵게/기울임/밑줄/크기/색상)은 ParaCharShape(문단 안에서 글자
 * 모양이 바뀌는 위치·글자모양ID 쌍의 목록)을 글자모양ID → DocInfo의
 * CharShape 레코드로 역참조해 얻는다(DEC-025 계열, Phase 3). 표 셀 내용은
 * 여전히 평문으로만 추출한다(표 자체가 DOCX에서는 이미 실제 표로 나가고
 * 있어 셀 서식까지는 이번 phase 범위 밖).
 *
 * 문단 정렬(DEC-040)은 문자 서식과 달리 CharShape이 아니라 ParaShape(문단
 * 단위 서식) 소관이라 항상 문단 전체에 하나만 있다 — ParaHeader의
 * paraShapeId로 DocInfo의 ParaShape을 역참조해 읽는다. HWP의 Distribute·
 * Divide(배분/나눔 정렬)는 DOCX에 대응 값이 없어 "justify"로 단순화한다
 * (문서화된 단순화, DEC-017과 같은 원칙).
 */
public class HwpToJson {
    // JSON 배열의 콤마 삽입 여부 — emitParagraph()가 표·머리말·글상자 등을 재귀로
    // 파고들며 여러 메서드에 걸쳐 블록을 추가하므로, 지역 변수 boolean 대신
    // 인스턴스 필드로 공유한다(이 클래스는 단일 실행에서 한 번만 쓰는 CLI 도구라
    // 스레드 안전성은 고려 대상이 아님).
    private boolean firstBlock = true;

    public static void main(String[] args) throws Exception {
        HWPFile hwp = HWPReader.fromFile(args[0]);
        DocInfo docInfo = hwp.getDocInfo();
        StringBuilder sb = new StringBuilder();
        sb.append("{\"blocks\":[");
        HwpToJson self = new HwpToJson();
        for (Section sec : hwp.getBodyText().getSectionList()) {
            for (int i = 0; i < sec.getParagraphCount(); i++) {
                self.emitParagraph(sec.getParagraph(i), docInfo, sb);
            }
        }
        sb.append("]}");
        Files.write(Paths.get(args[1]), sb.toString().getBytes(StandardCharsets.UTF_8));
    }

    /**
     * 문단 하나를 블록으로 내보내고, 그 문단이 담은 컨트롤(표·머리말·꼬리말·
     * 각주·미주·글상자)도 재귀로 처리한다. 재귀가 필요한 이유(외부 QA 이슈
     * #43 원인 조사로 발견): 머리말·글상자 같은 컨트롤이 항상 평문 문단만
     * 담는 게 아니라 **그 안에 표를 또 담을 수 있다** — 실사용 공공기관
     * 문서(mois-hwpplan.hwp)에서 결재란이 정확히 이 모양(머리말 → 표)이었다.
     * 표가 아닌 컨트롤만 처리하고 재귀하지 않으면 이런 중첩 구조의 텍스트가
     * 조용히 사라진다. 이전에는 ControlType.Table만 처리하고 나머지는 전부
     * 건너뛰어, 머리말·글상자 안의 문서 제목·결재란이 사라졌었다.
     * HwpToText.java의 TextExtractor는 InsertControlTextBetweenParagraphText
     * 옵션으로 이미 이 텍스트를 뽑아내고 있어 TXT 경로는 영향이 없었다.
     */
    private void emitParagraph(Paragraph p, DocInfo docInfo, StringBuilder sb) {
        String runsJson = paragraphRunsJson(p, docInfo);
        if (runsJson != null) {
            if (!firstBlock) sb.append(',');
            sb.append("{\"type\":\"p\",\"runs\":[").append(runsJson)
                    .append("],\"align\":\"").append(paragraphAlign(p, docInfo)).append("\"}");
            firstBlock = false;
        }
        if (p.getControlList() == null) return;
        for (Control c : p.getControlList()) {
            if (c.getType() == ControlType.Table) {
                emitTable((ControlTable) c, sb);
            } else if (c instanceof GsoControl) {
                emitGso((GsoControl) c, docInfo, sb);
            } else {
                ParagraphList nested = extractNestedParagraphList(c);
                if (nested == null) continue;
                for (Paragraph np : nested) {
                    emitParagraph(np, docInfo, sb);
                }
            }
        }
    }

    /**
     * 도형(Gso) 컨트롤의 텍스트를 재귀로 내보낸다. 묶음 개체(ControlContainer —
     * 여러 도형을 그룹으로 묶은 것)는 자기 자신은 텍스트가 없고 차일드 컨트롤
     * 목록만 갖는데, 그 차일드가 또 다른 묶음일 수도 있다(중첩 그룹) — 실사용
     * 문서(unikorea-contract.hwp)에서 서명란 텍스트가 정확히 이 묶음 개체
     * 안에 있었다(외부 QA 이슈 #43 재조사로 발견, 첫 수정에서는 놓쳤음).
     */
    private void emitGso(GsoControl gso, DocInfo docInfo, StringBuilder sb) {
        if (gso instanceof ControlContainer) {
            for (GsoControl child : ((ControlContainer) gso).getChildControlList()) {
                emitGso(child, docInfo, sb);
            }
            return;
        }
        TextBox tb = extractTextBoxFromGso(gso);
        if (tb == null) return;
        for (Paragraph np : tb.getParagraphList()) {
            emitParagraph(np, docInfo, sb);
        }
    }

    private void emitTable(ControlTable table, StringBuilder sb) {
        if (!firstBlock) sb.append(',');
        sb.append("{\"type\":\"table\",\"rows\":[");
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
        firstBlock = false;
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
        ArrayList<HWPChar> charList;
        try {
            charList = p.getText().getCharList();
        } catch (Exception e) {
            return null;
        }
        if (charList.isEmpty()) return null;
        int rawSize = charList.size();

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
            // ParaCharShape의 position은 "글자 1개=1칸"이 아니라
            // HWPChar.getCharSize()로 가중치를 매긴 값이다(예: 확장/인라인
            // 컨트롤 문자 — 하이퍼링크·각주·필드 등 — 는 charList에서 1칸만
            // 차지하지만 이 가중치로는 8로 셈) — charList의 실제 인덱스와
            // 다르다. 실사용 문서(distribution.hwp 문단 0의 섹션/컬럼정의
            // 확장문자 2개)에서 이 괴리로 뒷부분 위치가 charList 범위를
            // 넘어가는 것을 재현 확인(코드 리뷰로 발견) — 각 위치를 실제
            // charList 인덱스로 변환한 다음에 슬라이스한다.
            int[] rawPositions = new int[pairs.size()];
            for (int i = 0; i < pairs.size(); i++) {
                rawPositions[i] = weightedPositionToIndex(charList, (int) pairs.get(i).getPosition());
            }
            for (int i = 0; i < pairs.size(); i++) {
                int start = rawPositions[i];
                int end = (i + 1 < pairs.size()) ? rawPositions[i + 1] - 1 : rawSize - 1;
                if (start > end || start >= rawSize) continue;
                end = Math.min(end, rawSize - 1);
                String text;
                try {
                    text = extractNormalText(charList, start, end);
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
        // 결과를 내기 위함) — 이어붙인 전체 문자열 기준으로 앞뒤 공백 총량을
        // 구한 다음 run 경계를 넘나들며 그만큼만 제거한다. 물리적으로 첫/끝
        // 배열 원소만 다듬으면, 그 사이(예: 표제 문단 뒤에 공백만 있는
        // run)에 남는 공백을 놓친다(실사용 문서에서 재현 확인, 코드 리뷰로
        // 발견) — 그래서 "run 경계를 넘나들며" 처리한다.
        trimEdges(texts);

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

    /**
     * charList[start..end](양끝 포함)의 일반 글자만 이어붙인다.
     *
     * hwplib의 ParaText.getNormalString(start, end)를 쓰지 않는다 — 그
     * 메서드는 startIndex==endIndex(정확히 글자 1개짜리 범위)이면 무조건
     * 빈 문자열을 반환하는 버그가 있다(라이브러리 자체 소스로 확인). 이번
     * run 분리 기능이 처음으로 "글자 1개짜리 run"(예: 문단 중간의 공백 1개,
     * "⑤" 같은 단독 특수문자에만 다른 글자모양이 적용된 경우)을 실제로
     * 만들어내면서 실사용 문서(distribution.hwp)에서 재현 확인된 조용한
     * 텍스트 유실이었다(코드 리뷰로 발견) — 라이브러리를 우회해 직접
     * charList를 순회하는 것으로 수정.
     */
    private static String extractNormalText(ArrayList<HWPChar> charList, int start, int end) {
        StringBuilder sb = new StringBuilder();
        for (int i = start; i <= end && i < charList.size(); i++) {
            HWPChar ch = charList.get(i);
            if (ch.getType() == HWPCharType.Normal) {
                try {
                    sb.append(((HWPCharNormal) ch).getCh());
                } catch (Exception e) {
                    // 개별 글자 디코딩 실패는 그 글자만 건너뛴다(나머지는 보존).
                }
            }
        }
        return sb.toString();
    }

    /**
     * ParaCharShape의 가중치 위치(weightedPos, HWPChar.getCharSize() 합산
     * 기준)를 charList의 실제 인덱스로 변환한다. 가중치 누적 합이
     * weightedPos에 도달하는 첫 인덱스를 찾는다 — 끝까지 못 찾으면(위치가
     * 문단 끝을 넘어서면) charList.size()를 반환해 상위에서 "범위 밖"으로
     * 자연히 걸러지게 한다.
     */
    private static int weightedPositionToIndex(ArrayList<HWPChar> charList, int weightedPos) {
        int weight = 0;
        for (int i = 0; i < charList.size(); i++) {
            if (weight >= weightedPos) return i;
            weight += charList.get(i).getCharSize();
        }
        return charList.size();
    }

    /**
     * texts를 이어붙인 전체 문자열 기준으로 앞뒤 공백 총량을 구해, run
     * 경계를 넘나들며 그만큼만 정확히 제거한다(제자리 수정). 문단 중간의
     * 공백 run(단어 사이 구분자)은 건드리지 않는다.
     */
    private static void trimEdges(ArrayList<String> texts) {
        StringBuilder full = new StringBuilder();
        for (String t : texts) full.append(t);
        String joined = full.toString();
        int lead = 0;
        while (lead < joined.length() && Character.isWhitespace(joined.charAt(lead))) lead++;
        int trail = 0;
        while (trail < joined.length() - lead
                && Character.isWhitespace(joined.charAt(joined.length() - 1 - trail))) trail++;

        int remaining = lead;
        for (int i = 0; i < texts.size() && remaining > 0; i++) {
            String t = texts.get(i);
            if (t.length() <= remaining) {
                remaining -= t.length();
                texts.set(i, "");
            } else {
                texts.set(i, t.substring(remaining));
                remaining = 0;
            }
        }
        remaining = trail;
        for (int i = texts.size() - 1; i >= 0 && remaining > 0; i--) {
            String t = texts.get(i);
            if (t.length() <= remaining) {
                remaining -= t.length();
                texts.set(i, "");
            } else {
                texts.set(i, t.substring(0, t.length() - remaining));
                remaining = 0;
            }
        }
    }

    /**
     * 표·도형이 아닌 컨트롤에서 문단 리스트를 뽑아낸다(외부 QA 이슈 #43) —
     * 머리말·꼬리말·각주·미주는 Control 자체가 바로 문단 리스트를 갖는다.
     * 글상자(도형)는 구조가 더 복잡해(그룹 중첩 가능) emitGso()가 따로
     * 재귀 처리한다. 수식·양식 개체처럼 별도의 특수 구조를 쓰는 컨트롤은
     * 이번 범위 밖(정직하게 문서화 — 필요해지면 후속 과제)이라 null을
     * 반환해 건너뛴다.
     */
    private static ParagraphList extractNestedParagraphList(Control c) {
        if (c instanceof ControlHeader) return ((ControlHeader) c).getParagraphList();
        if (c instanceof ControlFooter) return ((ControlFooter) c).getParagraphList();
        if (c instanceof ControlFootnote) return ((ControlFootnote) c).getParagraphList();
        if (c instanceof ControlEndnote) return ((ControlEndnote) c).getParagraphList();
        return null;
    }

    private static TextBox extractTextBoxFromGso(GsoControl gso) {
        if (gso instanceof ControlRectangle) return ((ControlRectangle) gso).getTextBox();
        if (gso instanceof ControlEllipse) return ((ControlEllipse) gso).getTextBox();
        if (gso instanceof ControlPolygon) return ((ControlPolygon) gso).getTextBox();
        if (gso instanceof ControlCurve) return ((ControlCurve) gso).getTextBox();
        if (gso instanceof ControlArc) return ((ControlArc) gso).getTextBox();
        return null;
    }

    /**
     * 문단의 ParaShape에서 정렬을 읽어 DOCX 쪽 4값으로 단순화한다(DEC-040).
     * shapeId가 범위를 벗어나거나 Alignment를 못 읽으면 HWP 문서의 실제
     * 기본 정렬인 "justify"로 폴백한다 — "left"로 폴백하면 이 PR이 고치려던
     * "HWP 기본은 양쪽 정렬인데 DOCX 기본은 왼쪽 정렬"이라는 비대칭 문제가
     * 바로 이 방어 경로에서 재현된다(DEC-040 결정 로그 참고).
     */
    private static String paragraphAlign(Paragraph p, DocInfo docInfo) {
        int shapeId = p.getHeader().getParaShapeId();
        if (shapeId < 0 || shapeId >= docInfo.getParaShapeList().size()) return "justify";
        Alignment a = docInfo.getParaShapeList().get(shapeId).getProperty1().getAlignment();
        if (a == null) return "justify";
        switch (a) {
            case Left: return "left";
            case Center: return "center";
            case Right: return "right";
            case Justify: default: return "justify"; // Distribute·Divide도 여기로(문서화된 단순화)
        }
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
