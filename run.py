"""PyInstaller 엔트리 (상대 임포트 회피용 최상위 런처)."""
from app.main import main

if __name__ == "__main__":
    main()
