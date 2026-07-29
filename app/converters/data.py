"""데이터 변환 — CSV↔XLSX, CSV↔JSON (REQ-F-006). 한글 인코딩 자동 감지 (REQ-F-009 Should)."""
import csv
import json
from pathlib import Path

from .base import ConversionError

_ENCODINGS = ("utf-8-sig", "cp949", "utf-8")


def _read_text(path: Path) -> str:
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError:
            raise ConversionError("err.corrupted")
    raise ConversionError("err.encoding")


def _read_csv_rows(path: Path) -> list[list[str]]:
    text = _read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(text.splitlines(), dialect)]


def csv_to_xlsx(src: Path, tmpdir: Path) -> Path:
    from openpyxl import Workbook
    rows = _read_csv_rows(src)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    for row in rows:
        ws.append(row)
    out = tmpdir / (src.stem + ".xlsx")
    wb.save(out)
    return out


def xlsx_to_csv(src: Path, tmpdir: Path) -> Path:
    from openpyxl import load_workbook
    try:
        wb = load_workbook(src, read_only=True, data_only=True)
    except Exception as e:  # zip 손상, 암호화 등
        key = "err.password" if "encrypt" in str(e).lower() else "err.corrupted"
        raise ConversionError(key, str(e))
    ws = wb.active
    out = tmpdir / (src.stem + ".csv")
    # utf-8-sig: 엑셀에서 한글 깨짐 없이 열리도록 BOM 포함
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow(["" if v is None else v for v in row])
    wb.close()
    return out


def csv_to_json(src: Path, tmpdir: Path) -> Path:
    rows = _read_csv_rows(src)
    if not rows:
        records: list = []
    else:
        header, body = rows[0], rows[1:]
        records = [dict(zip(header, row)) for row in body]
    out = tmpdir / (src.stem + ".json")
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def json_to_csv(src: Path, tmpdir: Path) -> Path:
    try:
        payload = json.loads(_read_text(src))
    except json.JSONDecodeError as e:
        raise ConversionError("err.corrupted", str(e))
    if not isinstance(payload, list):
        raise ConversionError("err.jsonshape")

    out = tmpdir / (src.stem + ".csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if all(isinstance(r, dict) for r in payload):
            keys: list[str] = []
            for r in payload:
                for k in r:
                    if k not in keys:
                        keys.append(k)
            writer.writerow(keys)
            for r in payload:
                writer.writerow([r.get(k, "") for k in keys])
        elif all(isinstance(r, list) for r in payload):
            writer.writerows(payload)
        else:
            raise ConversionError("err.jsonshape")
    return out
