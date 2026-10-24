import shutil
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app" / "main.py")


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice ausente")
def test_app_runs_a_simulation_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    next(b for b in at.button if "Rodar" in b.label).click()
    at.run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert any("concluída" in s.value for s in at.success)
