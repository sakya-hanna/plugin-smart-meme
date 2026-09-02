import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.path_utils import resolve_image_path


def test_relative_image_path_resolves_under_image_root(tmp_path):
    root = tmp_path / 'images'
    root.mkdir()
    image = root / 'sample.png'
    image.write_bytes(b'png')
    assert resolve_image_path('sample.png', root) == image.resolve()


def test_image_path_rejects_escape_and_missing_file(tmp_path):
    root = tmp_path / 'images'
    root.mkdir()
    assert resolve_image_path('../sample.png', root) is None
    assert resolve_image_path('missing.png', root) is None
