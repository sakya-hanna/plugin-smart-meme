from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from PIL import Image

@dataclass
class StoredImage:
    id: int | None
    path: str
    stored_filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str

class ImageStore:
    ALLOWED={".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",".webp":"image/webp",".gif":"image/gif"}
    def __init__(self, root, max_bytes=10*1024*1024):
        self.root=Path(root); self.images=self.root/"images"; self.images.mkdir(parents=True,exist_ok=True); self.max_bytes=max_bytes
    def save(self, data: bytes, original_filename: str):
        if not data or len(data)>self.max_bytes: raise ValueError("图片为空或超过大小限制")
        suffix=Path(original_filename).suffix.lower()
        if suffix not in self.ALLOWED: raise ValueError("不支持的图片格式")
        try:
            from io import BytesIO
            with Image.open(BytesIO(data)) as img: img.verify()
        except Exception as exc: raise ValueError("无效的图片文件") from exc
        digest=sha256(data).hexdigest(); stored=f"{uuid4().hex}{suffix}"; target=self.images/stored; tmp=self.images/f".{stored}.tmp"
        tmp.write_bytes(data)
        try:
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True); raise
        return StoredImage(None,str(target),stored,original_filename,self.ALLOWED[suffix],len(data),digest)
