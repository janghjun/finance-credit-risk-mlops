# tests/conftest.py
import os
import sys
from pathlib import Path
import pytest


@pytest.fixture(scope="session", autouse=True)
def set_project_root_and_path():
    """프로젝트 루트를 작업 디렉토리로 바꾸고, sys.path에 추가."""
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)  # pytest 실행 위치 무관
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))  # ← 핵심: 루트를 import 경로에 추가
