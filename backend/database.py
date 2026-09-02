from __future__ import annotations

import random
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS images(
    id INTEGER PRIMARY KEY,
    stored_filename TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    sha256 TEXT,
    content_description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tags(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('emotion','content')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, kind)
);
CREATE TABLE IF NOT EXISTS image_tags(
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY(image_id, tag_id)
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
            self._migrate_content_descriptions(con)

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _migrate_content_descriptions(self, con):
        columns = {row[1] for row in con.execute("PRAGMA table_info(images)")}
        if "content_description" not in columns:
            con.execute("ALTER TABLE images ADD COLUMN content_description TEXT NOT NULL DEFAULT ''")
        old_content = con.execute(
            """SELECT it.image_id, t.name FROM image_tags it JOIN tags t ON t.id=it.tag_id
               WHERE t.kind='content' ORDER BY it.image_id, it.tag_id"""
        ).fetchall()
        for image_id, name in old_content:
            con.execute(
                "UPDATE images SET content_description=? WHERE id=? AND (content_description IS NULL OR content_description='')",
                (name, image_id),
            )
        con.execute("DELETE FROM image_tags WHERE tag_id IN (SELECT id FROM tags WHERE kind='content')")
        con.execute("DELETE FROM tags WHERE kind='content'")

    def create_tag(self, name, kind="emotion"):
        if kind != "emotion" or not isinstance(name, str) or not name or name != name.strip():
            raise ValueError("只能创建有效的情绪标签")
        with self.connect() as c:
            c.execute("INSERT INTO tags(name,kind) VALUES(?,?)", (name, kind))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def list_tags(self, kind=None):
        with self.connect() as c:
            q = "SELECT id,name,kind FROM tags WHERE kind='emotion'"
            args = []
            if kind:
                if kind != "emotion":
                    return []
                q += " AND kind=?"
                args.append(kind)
            return [dict(x) for x in c.execute(q + " ORDER BY id", args)]

    def active_tags(self, kind=None):
        with self.connect() as c:
            q="SELECT DISTINCT t.id,t.name,t.kind FROM tags t JOIN image_tags it ON it.tag_id=t.id JOIN images i ON i.id=it.image_id WHERE i.enabled=1 AND t.kind='emotion'"
            args=[]
            if kind:
                if kind != 'emotion': return []
                q += ' AND t.kind=?'; args.append(kind)
            return [dict(x) for x in c.execute(q+' ORDER BY t.name',args)]

    def active_image_pairs(self):
        with self.connect() as c:
            rows = c.execute(
                """SELECT DISTINCT t.name AS emotion, i.content_description AS content
                   FROM images i JOIN image_tags it ON it.image_id=i.id
                   JOIN tags t ON t.id=it.tag_id
                   WHERE i.enabled=1 AND t.kind='emotion' AND i.content_description<>''
                   ORDER BY t.name, i.content_description"""
            ).fetchall()
            return [(row["emotion"], row["content"]) for row in rows]

    def create_image(self, stored_filename, path, enabled=True, mime_type="", size_bytes=0, sha256="", content_description="", original_filename=None):
        description = str(content_description).strip()
        if not description:
            raise ValueError("内容描述不能为空")
        with self.connect() as c:
            c.execute(
                """INSERT INTO images(stored_filename,original_filename,path,mime_type,size_bytes,enabled,sha256,content_description)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (stored_filename, original_filename or stored_filename, path, mime_type, size_bytes, int(enabled), sha256, description),
            )
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    def create_image_with_tags(self, stored_filename, path, tag_ids, enabled=True, mime_type="", size_bytes=0, sha256="", content_description="", original_filename=None):
        description = str(content_description).strip()
        if not description:
            raise ValueError("内容描述不能为空")
        ids = [int(x) for x in tag_ids]
        if not ids:
            raise ValueError("至少需要一个情绪标签")
        with self.connect() as c:
            marks = ",".join("?" * len(ids))
            rows = c.execute(f"SELECT id,kind FROM tags WHERE id IN ({marks})", ids).fetchall()
            if len(rows) != len(set(ids)) or {row[1] for row in rows} != {"emotion"}:
                raise ValueError("图片只能关联有效的情绪标签")
            c.execute(
                """INSERT INTO images(stored_filename,original_filename,path,mime_type,size_bytes,enabled,sha256,content_description)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (stored_filename, original_filename or stored_filename, path, mime_type, size_bytes, int(enabled), sha256, description),
            )
            image_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            c.executemany("INSERT INTO image_tags(image_id,tag_id) VALUES(?,?)", [(image_id, x) for x in dict.fromkeys(ids)])
            return image_id

    def attach_tag(self, image_id, tag_id):
        with self.connect() as c:
            kind = c.execute("SELECT kind FROM tags WHERE id=?", (tag_id,)).fetchone()
            if not kind or kind[0] != "emotion":
                raise ValueError("图片只能关联情绪标签")
            c.execute("INSERT OR IGNORE INTO image_tags VALUES(?,?)", (image_id, tag_id))

    def related_content_descriptions(self, known_emotion_id):
        with self.connect() as c:
            rows = c.execute(
                """SELECT DISTINCT i.content_description FROM images i
                   JOIN image_tags it ON it.image_id=i.id
                   WHERE it.tag_id=? AND i.enabled=1 AND i.content_description<>''
                   ORDER BY i.content_description""",
                (known_emotion_id,),
            ).fetchall()
            return [r[0] for r in rows]

    def related_emotion_names(self, content_description):
        with self.connect() as c:
            rows = c.execute(
                """SELECT DISTINCT t.name FROM tags t JOIN image_tags it ON it.tag_id=t.id
                   JOIN images i ON i.id=it.image_id
                   WHERE i.enabled=1 AND t.kind='emotion' AND i.content_description=? ORDER BY t.name""",
                (content_description,),
            ).fetchall()
            return [r[0] for r in rows]

    def matching_images(self, emotion, content):
        with self.connect() as c:
            rows = c.execute(
                """SELECT DISTINCT i.* FROM images i JOIN image_tags it ON it.image_id=i.id
                   JOIN tags e ON e.id=it.tag_id
                   WHERE i.enabled=1 AND e.kind='emotion' AND e.name=? AND i.content_description=?""",
                (emotion, content),
            ).fetchall()
            return [dict(r) for r in rows]

    def rename_tag(self, tag_id, name):
        name = str(name).strip()
        if not name:
            raise ValueError("标签名称不能为空")
        with self.connect() as c:
            row = c.execute("SELECT kind FROM tags WHERE id=?", (tag_id,)).fetchone()
            if not row or row[0] != "emotion":
                raise ValueError("情绪标签不存在")
            c.execute("UPDATE tags SET name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (name, tag_id))

    def delete_tag(self, tag_id):
        with self.connect() as c:
            used = c.execute("SELECT COUNT(*) FROM image_tags WHERE tag_id=?", (tag_id,)).fetchone()[0]
            if used:
                raise ValueError(f"标签仍被 {used} 张图片使用")
            c.execute("DELETE FROM tags WHERE id=?", (tag_id,))

    def set_image_enabled(self, image_id, enabled):
        with self.connect() as c:
            c.execute("UPDATE images SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(enabled), image_id))

    def set_images_enabled(self, image_ids, enabled):
        ids=[int(x) for x in image_ids]
        if not ids: return
        with self.connect() as c:
            c.executemany("UPDATE images SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", [(int(enabled),x) for x in ids])

    def update_image(self, image_id, tag_ids, content_description):
        description = str(content_description).strip()
        if not description:
            raise ValueError("内容描述不能为空")
        with self.connect() as c:
            kinds = {r[0] for r in c.execute("SELECT kind FROM tags WHERE id IN (%s)" % ",".join("?" * len(tag_ids)), tag_ids)} if tag_ids else set()
            if not tag_ids or not kinds or kinds != {"emotion"}:
                raise ValueError("至少需要一个情绪标签")
            if not c.execute("SELECT 1 FROM images WHERE id=?", (image_id,)).fetchone():
                raise ValueError("图片不存在")
            c.execute("DELETE FROM image_tags WHERE image_id=?", (image_id,))
            c.executemany("INSERT INTO image_tags(image_id,tag_id) VALUES(?,?)", [(image_id, x) for x in tag_ids])
            c.execute("UPDATE images SET content_description=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (description, image_id))

    def delete_image(self, image_id):
        with self.connect() as c:
            row = c.execute("SELECT path FROM images WHERE id=?", (image_id,)).fetchone()
            c.execute("DELETE FROM images WHERE id=?", (image_id,))
            return row[0] if row else None

    def delete_images(self, image_ids):
        ids=[int(x) for x in image_ids]
        if not ids: return []
        marks=",".join("?"*len(ids))
        with self.connect() as c:
            paths=[r[0] for r in c.execute(f"SELECT path FROM images WHERE id IN ({marks})",ids)]
            c.execute(f"DELETE FROM images WHERE id IN ({marks})",ids)
            return paths

    def list_images(self, enabled=None, emotion=None, content=None, filename=None):
        q = "SELECT DISTINCT i.* FROM images i"
        args, where = [], []
        if emotion:
            q += " JOIN image_tags it ON it.image_id=i.id JOIN tags t ON t.id=it.tag_id"
            where.append("t.kind='emotion' AND t.name=?")
            args.append(emotion)
        if enabled is not None:
            where.append("i.enabled=?")
            args.append(int(enabled))
        if content:
            where.append("i.content_description LIKE ?")
            args.append(f"%{content}%")
        if filename:
            where.append("i.original_filename LIKE ?")
            args.append(f"%{filename}%")
        if where:
            q += " WHERE " + " AND ".join(where)
        with self.connect() as c:
            rows = [dict(x) for x in c.execute(q + " ORDER BY i.id DESC", args)]
            for row in rows:
                row["emotion_tags"] = [r[0] for r in c.execute("SELECT t.name FROM tags t JOIN image_tags it ON it.tag_id=t.id WHERE it.image_id=? ORDER BY t.name", (row["id"],))]
            return rows
