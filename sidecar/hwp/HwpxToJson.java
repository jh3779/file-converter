import kr.dogfoot.hwpxlib.object.HWPXFile;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.HorizontalAlign2;
import kr.dogfoot.hwpxlib.object.content.header_xml.enumtype.UnderlineType;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.CharPr;
import kr.dogfoot.hwpxlib.object.content.header_xml.references.ParaPr;
import kr.dogfoot.hwpxlib.object.content.section_xml.ParaListCore;
import kr.dogfoot.hwpxlib.object.content.section_xml.SectionXMLFile;
import kr.dogfoot.hwpxlib.object.content.section_xml.SubList;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Para;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.Run;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.RunItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.T;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.TItem;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.Table;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tc;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.object.table.Tr;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.FWSpace;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.LineBreak;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NBSpace;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.NormalText;
import kr.dogfoot.hwpxlib.object.content.section_xml.paragraph.t.Tab;
import kr.dogfoot.hwpxlib.reader.HWPXReader;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;

/**
 * HWPX → 구조 JSON 사이드카(Phase 1: QA(h) 외부 요청, Phase 2: DEC-049
 * HWPX 쓰기 착수에 맞춰 표 병합·정렬 읽기 확장). 사용:
 * java HwpxToJson <in.hwpx> <out.json>
 * 출력 스키마는 HwpToJson.java(HWP용)와 동일 — DOCX 쪽(docx_build.py)이
 * 포맷 구분 없이 그대로 재사용할 수 있게 맞췄다:
 * {"blocks":[
 *   {"type":"p","runs":[{"text":"...","bold":bool,"italic":bool,"underline":bool,"size":pt,"color":"RRGGBB"}],
 *     "align":"left"|"center"|"right"|"justify"} |
 *   {"type":"table","rows":[["c1",{"text":"c2","colSpan":2,"rowSpan":1},...],...]}
 * ]}
 *
 * hwpxlib(Apache-2.0, neolord0)의 객체 모델은 hwplib보다 문자 서식 추출이
 * 더 단순하다 — 문단 안 위치를 가중치로 역산해야 했던 HWP(ParaCharShape)와
 * 달리, HWPX는 각 Run이 자기 charPrIDRef를 직접 갖고 있어(문단(Para) →
 * 런(Run, 서식 단위) → 런아이템(RunItem: 텍스트 T 또는 표 Table)) run
 * 경계가 이미 XML 구조 자체에 있다. 표는 Ctrl로 감싸이지 않고 Table이
 * RunItem으로 직접 들어간다(hwplib의 "표는 별도 컨트롤 목록" 구조와 다름) —
 * 한 문단 안에 텍스트와 표가 섞여 있을 수 있어 run을 순서대로 훑다가
 * Table을 만나면 그때까지 모은 텍스트 run들을 먼저 문단 블록으로 내보내고
 * 표 블록을 낸 뒤 계속한다.
 *
 * 표 셀 병합 정보(colSpan/rowSpan, DEC-049)를 함께 낸다 — 병합 없는(1×1)
 * 흔한 경우는 기존과 똑같이 평문 문자열로, 실제 병합된 셀만 객체로 낸다
 * (HwpToJson.java의 DEC-035와 동일한 원칙). 병합된 셀이 덮는 자리는
 * hwpxlib 자체가 애초에 `Tc`를 만들지 않는 sparse 표현이라(스파이크로
 * 확인, spike/hwpxlib/RESULT.md "Phase 2(쓰기)" 참고) 별도 재구성 로직
 * 없이 `Tr.getTc()`를 그대로 순회하면 된다.
 *
 * 문단 정렬(align, DEC-049)도 함께 낸다 — HwpToJson.java의 DEC-040과
 * 동일한 원칙(HWP의 Distribute·Divide처럼 hwpxlib의 DISTRIBUTE·
 * DISTRIBUTE_SPACE도 DOCX에 대응 값이 없어 "justify"로 단순화).
 *
 * **쪽 나눔(pageBreakBefore)은 의도적으로 이 정식 스키마에 넣지 않는다** —
 * HwpToJson.java도 이 값을 안 보고(HWP는 PageBreakDebug.java라는 별도
 * 디버그 전용 도구로만 확인, DEC-039), HWPX 쪽 회귀 검증은 이와 대칭인
 * PageBreakDebugHwpx.java를 쓴다.
 */
public class HwpxToJson {
    private boolean firstBlock = true;

    public static void main(String[] args) throws Exception {
        HWPXFile hwpx = HWPXReader.fromFilepath(args[0]);
        StringBuilder sb = new StringBuilder();
        sb.append("{\"blocks\":[");
        HwpxToJson self = new HwpxToJson();
        for (SectionXMLFile section : hwpx.sectionXMLFileList().items()) {
            for (Para p : section.paras()) {
                self.emitParagraph(hwpx, p, sb);
            }
        }
        sb.append("]}");
        Files.write(Paths.get(args[1]), sb.toString().getBytes(StandardCharsets.UTF_8));
    }

    /** 문단 하나를 훑으며 run(텍스트+서식)을 모으고, 표를 만나면 그 시점까지
     * 모은 run을 문단 블록으로 먼저 내보낸 뒤 표 블록을 낸다. */
    private void emitParagraph(HWPXFile hwpx, Para p, StringBuilder sb) throws Exception {
        ArrayList<String> texts = new ArrayList<>();
        ArrayList<CharPr> shapes = new ArrayList<>();

        for (int ri = 0; ri < p.countOfRun(); ri++) {
            Run run = p.getRun(ri);
            CharPr charPr = resolveCharPr(hwpx, run.charPrIDRef());
            StringBuilder runText = new StringBuilder();
            for (int ii = 0; ii < run.countOfRunItem(); ii++) {
                RunItem item = run.getRunItem(ii);
                if (item instanceof T) {
                    runText.append(extractTextFrom((T) item));
                } else if (item instanceof Table) {
                    if (runText.length() > 0) {
                        texts.add(runText.toString());
                        shapes.add(charPr);
                        runText = new StringBuilder();
                    }
                    emitParagraphBlock(texts, shapes, p, hwpx, sb);
                    texts = new ArrayList<>();
                    shapes = new ArrayList<>();
                    emitTable(hwpx, (Table) item, sb);
                }
                // 그 외 RunItem(도형·수식·필드 등)은 이번 phase 범위 밖 —
                // 텍스트 보존은 항상 우선이므로 건너뛰고 계속 진행한다.
            }
            if (runText.length() > 0) {
                texts.add(runText.toString());
                shapes.add(charPr);
            }
        }
        emitParagraphBlock(texts, shapes, p, hwpx, sb);
    }

    private void emitParagraphBlock(ArrayList<String> texts, ArrayList<CharPr> shapes, Para p,
                                     HWPXFile hwpx, StringBuilder sb) {
        trimEdges(texts);
        StringBuilder runsJson = new StringBuilder();
        boolean firstRun = true;
        for (int i = 0; i < texts.size(); i++) {
            if (texts.get(i).isEmpty()) continue;
            if (!firstRun) runsJson.append(',');
            runsJson.append(runJson(texts.get(i), shapes.get(i)));
            firstRun = false;
        }
        if (firstRun) return; // 빈 문단 — 블록 자체를 건너뜀(기존 HwpToJson.java와 동일한 원칙)
        if (!firstBlock) sb.append(',');
        sb.append("{\"type\":\"p\",\"runs\":[").append(runsJson)
                .append("],\"align\":\"").append(paragraphAlign(hwpx, p)).append("\"}");
        firstBlock = false;
    }

    private void emitTable(HWPXFile hwpx, Table table, StringBuilder sb) throws Exception {
        if (!firstBlock) sb.append(',');
        sb.append("{\"type\":\"table\",\"rows\":[");
        boolean firstRow = true;
        for (int ri = 0; ri < table.countOfTr(); ri++) {
            Tr tr = table.getTr(ri);
            if (!firstRow) sb.append(',');
            sb.append('[');
            boolean firstCell = true;
            for (int ci = 0; ci < tr.countOfTc(); ci++) {
                Tc tc = tr.getTc(ci);
                if (!firstCell) sb.append(',');
                String cellText = extractPlainText(tc.subList());
                int colSpan = (tc.cellSpan() != null && tc.cellSpan().colSpan() != null)
                        ? tc.cellSpan().colSpan() : 1;
                int rowSpan = (tc.cellSpan() != null && tc.cellSpan().rowSpan() != null)
                        ? tc.cellSpan().rowSpan() : 1;
                if (colSpan <= 1 && rowSpan <= 1) {
                    sb.append('"').append(esc(cellText)).append('"');
                } else {
                    sb.append("{\"text\":\"").append(esc(cellText)).append('"')
                            .append(",\"colSpan\":").append(colSpan)
                            .append(",\"rowSpan\":").append(rowSpan).append('}');
                }
                firstCell = false;
            }
            sb.append(']');
            firstRow = false;
        }
        sb.append("]}");
        firstBlock = false;
    }

    /** 셀 안 문단들의 텍스트만 평문으로 이어붙인다(서식·중첩 표는 범위 밖 —
     * hwplib 쪽 emitTable의 safeText()와 같은 원칙). */
    private static String extractPlainText(ParaListCore list) throws Exception {
        StringBuilder sb = new StringBuilder();
        for (Para p : list.paras()) {
            StringBuilder paraText = new StringBuilder();
            for (int ri = 0; ri < p.countOfRun(); ri++) {
                Run run = p.getRun(ri);
                for (int ii = 0; ii < run.countOfRunItem(); ii++) {
                    RunItem item = run.getRunItem(ii);
                    if (item instanceof T) {
                        paraText.append(extractTextFrom((T) item));
                    }
                }
            }
            String trimmed = paraText.toString().trim();
            if (trimmed.isEmpty()) continue;
            if (sb.length() > 0) sb.append('\n');
            sb.append(trimmed);
        }
        return sb.toString();
    }

    /** T(텍스트 run item)에서 실제 문자열을 뽑는다 — 단순 텍스트(onlyText)
     * 또는 TItem 목록(NormalText·LineBreak·Tab 등 섞인 경우) 둘 다 처리.
     * 줄바꿈·탭·빈칸류는 PDF 파이프라인과 같은 원칙으로 공백 하나로
     * 정규화한다(문단 경계는 이미 Para 단위로 나뉘어 있어 내부 줄바꿈은
     * 단어 구분자 역할일 뿐). Tab/FWSpace/NBSpace를 빼먹으면 그 앞뒤
     * 텍스트가 공백 없이 그대로 붙어버린다(회귀로 발견해 수정 — PR
     * 콘텐츠 리뷰). 변경추적 마크 등 그 외 TItem 종류는 이번 phase 범위 밖.
     */
    private static String extractTextFrom(T t) {
        if (t.onlyText() != null) return t.onlyText();
        if (t.items() == null) return "";
        StringBuilder sb = new StringBuilder();
        for (TItem item : t.items()) {
            if (item instanceof NormalText) {
                sb.append(((NormalText) item).text());
            } else if (item instanceof LineBreak || item instanceof Tab
                    || item instanceof FWSpace || item instanceof NBSpace) {
                sb.append(' ');
            }
        }
        return sb.toString();
    }

    private static CharPr resolveCharPr(HWPXFile hwpx, String charPrIDRef) {
        if (charPrIDRef == null) return null;
        for (CharPr cp : hwpx.headerXMLFile().refList().charProperties().items()) {
            if (charPrIDRef.equals(cp.id())) return cp;
        }
        return null;
    }

    /** HwpToJson.java의 paragraphAlign()과 동일한 원칙(DEC-040 대칭,
     * DEC-049) — 정보 없음/알 수 없는 값은 hwpxlib 기본 ParaPr(id=3,
     * BlankFileMaker가 만드는 양쪽 정렬)과 같은 "justify"로 폴백해,
     * HWP 쪽에서 이미 겪은 "DOCX 기본은 왼쪽인데 왼쪽으로 잘못 폴백하면
     * 어긋난다"는 문제를 똑같이 피한다. */
    private static String paragraphAlign(HWPXFile hwpx, Para p) {
        ParaPr pr = resolveParaPr(hwpx, p.paraPrIDRef());
        if (pr == null || pr.align() == null || pr.align().horizontal() == null) return "justify";
        HorizontalAlign2 a = pr.align().horizontal();
        switch (a) {
            case LEFT: return "left";
            case CENTER: return "center";
            case RIGHT: return "right";
            case JUSTIFY:
            default: return "justify"; // DISTRIBUTE·DISTRIBUTE_SPACE도 여기로(문서화된 단순화)
        }
    }

    private static ParaPr resolveParaPr(HWPXFile hwpx, String paraPrIDRef) {
        if (paraPrIDRef == null) return null;
        for (ParaPr pr : hwpx.headerXMLFile().refList().paraProperties().items()) {
            if (paraPrIDRef.equals(pr.id())) return pr;
        }
        return null;
    }

    private static String runJson(String text, CharPr cp) {
        boolean bold = false, italic = false, underline = false;
        double sizePt = 10.0;
        String color = "000000";
        if (cp != null) {
            bold = cp.bold() != null;
            italic = cp.italic() != null;
            // bold/italic과 달리 Underline은 "밑줄 없음"도 명시적 객체(type=NONE)로
            // 표현된다(존재 자체가 신호인 bold/italic과 다름) — 로컬 검증 중
            // 모든 run에 underline=true로 잘못 나오는 것을 재현해 발견.
            underline = cp.underline() != null && cp.underline().type() != UnderlineType.NONE;
            // height는 hwpunit(pt*100) 단위 — hwplib CharShape.getBaseSize()와 같은 단위계.
            if (cp.height() != null) sizePt = cp.height() / 100.0;
            if (cp.textColor() != null && cp.textColor().matches("(?i)#?[0-9A-F]{6}")) {
                color = cp.textColor().replace("#", "").toUpperCase();
            }
        }
        return "{\"text\":\"" + esc(text) + "\",\"bold\":" + bold + ",\"italic\":" + italic
                + ",\"underline\":" + underline + ",\"size\":" + sizePt + ",\"color\":\"" + color + "\"}";
    }

    /** HwpToJson.java의 trimEdges()와 동일한 원칙 — run 경계를 넘나들며
     * 문단 전체 기준 앞뒤 공백만 정확히 제거한다. */
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
