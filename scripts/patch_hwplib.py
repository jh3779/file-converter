"""hwplib main 브랜치를 JDK 11+에서 컴파일 가능하게 패치 (spike/hwplib/RESULT.md 절차).

사용: python scripts/patch_hwplib.py <hwplib 소스 루트>
"""
import sys
from pathlib import Path

root = Path(sys.argv[1])

reader = root / "src/main/java/kr/dogfoot/hwplib/reader/HWPReader.java"
s = reader.read_text(encoding="utf-8")
s = s.replace("import javax.xml.bind.DatatypeConverter;\n", "")
s = s.replace("DatatypeConverter.parseBase64Binary(base64)",
              "java.util.Base64.getDecoder().decode(base64)")
reader.write_text(s, encoding="utf-8")

fordocinfo = root / "src/main/java/kr/dogfoot/hwplib/writer/autosetter/ForDocInfo.java"
s = fordocinfo.read_text(encoding="utf-8")
s = s.replace("import com.sun.jmx.snmp.agent.SnmpUserDataFactory;\n", "")
fordocinfo.write_text(s, encoding="utf-8")

print("patched:", reader.name, fordocinfo.name)
