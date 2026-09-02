import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from PIL import Image
from backend.image_store import ImageStore


def test_image_store_validates_real_image_and_unique_name(tmp_path):
    store = ImageStore(tmp_path, max_bytes=1024 * 1024)
    buf = io.BytesIO(); Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
    record = store.save(buf.getvalue(), "中文.png")
    assert record.original_filename == "中文.png"
    assert Path(record.path).exists()


def test_image_store_rejects_fake_image(tmp_path):
    store = ImageStore(tmp_path, max_bytes=100)
    try:
        store.save(b"not an image", "x.png")
    except ValueError as exc:
        assert "图片" in str(exc)
    else:
        raise AssertionError("fake image was accepted")


def test_image_store_accepts_gif(tmp_path):
    store = ImageStore(tmp_path, max_bytes=1024 * 1024)
    buf = io.BytesIO(); Image.new("P", (2, 2), 1).save(buf, format="GIF")
    record = store.save(buf.getvalue(), "animated.gif")
    assert record.mime_type == "image/gif"
    assert Path(record.path).suffix == ".gif"
