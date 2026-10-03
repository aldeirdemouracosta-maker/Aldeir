import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frameltx.config import AppConfig  # noqa: E402


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    c = AppConfig(output_dir=tmp_path / "out", demo_mode=True, export_width=216, export_height=384)
    c.output_dir.mkdir()
    return c


@pytest.fixture
def image(tmp_path: Path) -> Path:
    path = tmp_path / "input.png"
    Image.new("RGB", (360, 640), (200, 80, 120)).save(path)
    return path
