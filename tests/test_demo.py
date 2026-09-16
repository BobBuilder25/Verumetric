"""The demo doubles as an end-to-end smoke test of the free ladder.

It renders a SYNTHETIC receipt, reads it with a real OCR engine, and checks that
an honest reading certifies while three deliberate defects do not. Skipped where
no OCR engine is installed; the rest of the suite needs none.
"""

from __future__ import annotations

import shutil
import sys

import pytest

pytest.importorskip("PIL")
if shutil.which("tesseract") is None:
    pytest.skip("no OCR engine installed", allow_module_level=True)

sys.path.insert(0, "tools")


def test_the_free_ladder_certifies_honest_work_and_catches_the_three_defects(tmp_path, capsys):
    import demo

    assert demo.main(["--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "honest reading" in out and "pass" in out
    assert "fail_retry" in out


def test_it_also_holds_on_a_degraded_page(tmp_path, capsys):
    """The contamination defence rotates and blurs every page, so the ladder has
    to work on the degraded version - that is the version T-metrics come from."""
    import demo

    assert demo.main(["--augmented", "--out", str(tmp_path)]) == 0
