"""Shared fixtures available to all test modules."""
import io
import pytest
from pathlib import Path
from PIL import Image


@pytest.fixture(scope="session")
def fixture_screenshot_dir(tmp_path_factory) -> Path:
    """
    Creates a small but valid PNG screenshot in a temp directory.
    Used by extraction tests as a stand-in for a real product page screenshot.
    """
    d = tmp_path_factory.mktemp("screenshots")
    _make_png(d / "chewy_nexgard-10-24lb-6pk.png")
    _make_png(d / "petmeds_nexgard-10-24lb-6pk.png")
    return d


def _make_png(path: Path) -> None:
    """Write a minimal 100x100 white PNG to path."""
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())
