from __future__ import annotations
import asyncio
import base64
import tempfile
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.api.web import error_response, json_response, request, file_response

from .backend.service import SmartMemeService
from .backend.matching import keyword_match, probability_hit
from .backend.path_utils import resolve_image_path

PLUGIN_NAME = "astrbot_plugin_smart_meme"

class Main(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config=dict(config or {})
        data_dir=Path(get_astrbot_data_path()) / "plugin_data" / self.name
        data_dir.mkdir(parents=True, exist_ok=True)
        self.service=SmartMemeService(data_dir, self.config)
        self.service.context=context
        self._seed_tags()
        for route, handler, methods, desc in [
            (f"/{PLUGIN_NAME}/tags", self.api_tags, ["GET"], "List tags"),
            (f"/{PLUGIN_NAME}/tags", self.api_create_tag, ["POST"], "Create tag"),
            (f"/{PLUGIN_NAME}/tags/<tag_id>", self.api_update_tag, ["PUT"], "Rename tag"),
            (f"/{PLUGIN_NAME}/tags/<tag_id>/rename", self.api_update_tag, ["POST"], "Rename tag"),
            (f"/{PLUGIN_NAME}/tags/<tag_id>", self.api_delete_tag, ["DELETE"], "Delete tag"),
            (f"/{PLUGIN_NAME}/tags/<tag_id>/delete", self.api_delete_tag, ["POST"], "Delete tag"),
            (f"/{PLUGIN_NAME}/images", self.api_images, ["GET"], "List images"),
            (f"/{PLUGIN_NAME}/images/batch/enabled", self.api_images_batch_enabled, ["POST"], "Enable or disable selected images"),
            (f"/{PLUGIN_NAME}/images/batch/delete", self.api_images_batch_delete, ["POST"], "Delete selected images"),
            (f"/{PLUGIN_NAME}/images/<image_id>/file", self.api_image_file, ["GET"], "Preview image"),
            (f"/{PLUGIN_NAME}/images/<image_id>/preview", self.api_image_preview, ["GET"], "Preview image data"),
            (f"/{PLUGIN_NAME}/images/<image_id>/tags", self.api_image_tags, ["PUT", "POST"], "Edit image emotion tags and description"),
            (f"/{PLUGIN_NAME}/images/<image_id>/enabled", self.api_image_enabled, ["POST"], "Enable image"),
            (f"/{PLUGIN_NAME}/images/<image_id>", self.api_delete_image, ["DELETE"], "Delete image"),
            (f"/{PLUGIN_NAME}/images/<image_id>/delete", self.api_delete_image, ["POST"], "Delete image"),
            (f"/{PLUGIN_NAME}/upload", self.api_upload, ["POST"], "Upload image"),
            (f"/{PLUGIN_NAME}/upload/commit", self.api_upload_commit, ["POST"], "Commit image upload"),
        ]:
            context.register_web_api(route, handler, methods, desc)

    def _seed_tags(self):
        defaults={"emotion":["开心","愤怒","无奈","悲伤","疑惑","嫌弃","期待","骄傲","害羞","惊讶","震惊","恐惧","紧张","尴尬","委屈","失望","感动","兴奋","疲惫","撒娇"]}
        for kind,names in defaults.items():
            existing={x["name"] for x in self.service.db.list_tags(kind)}
            for name in names:
                if name not in existing:
                    try: self.service.db.create_tag(name,kind)
                    except Exception: logger.exception("初始化标签失败")

    def _admin_required(self):
        username=getattr(request,"username",None)
        return bool(username)

    @staticmethod
    def _positive_id(value):
        try:
            value=int(value)
        except (TypeError,ValueError):
            return None
        return value if value>0 else None

    @staticmethod
    def _json_object(data):
        return data if isinstance(data,dict) else None

    @staticmethod
    def _is_plugin_llm_result(event):
        origin=event.get_extra("meme_manager_llm_request_origin", None)
        if origin in {"plugin", "plugin_llm"}: return True
        return bool(event.get_extra("smart_meme_plugin_llm", False))

    async def api_tags(self):
        if not self._admin_required(): return error_response("需要管理员登录", 403)
        return json_response({"tags":self.service.db.list_tags()})

    async def api_images(self):
        if not self._admin_required(): return error_response("需要管理员登录", 403)
        q=request.query
        enabled=q.get("enabled")
        enabled=None if enabled in (None,"all","") else enabled.lower() in ("1","true","yes")
        return json_response({"images":self.service.db.list_images(enabled, q.get("emotion"), q.get("content"), q.get("filename"))})

    async def api_image_file(self, image_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        image_id=self._positive_id(image_id)
        if image_id is None: return error_response("图片 ID 非法",400)
        with self.service.db.connect() as c: row=c.execute("SELECT path FROM images WHERE id=?",(image_id,)).fetchone()
        if not row: return error_response("图片不存在",404)
        path=Path(row[0])
        if not path.is_absolute(): path=self.service.store.images/path.name
        path=path.resolve()
        if self.service.store.images.resolve() not in path.parents or not path.is_file(): return error_response("图片路径非法",404)
        return file_response(str(path))

    async def api_image_preview(self, image_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        image_id=self._positive_id(image_id)
        if image_id is None: return error_response("图片 ID 非法",400)
        with self.service.db.connect() as c: row=c.execute("SELECT path,mime_type FROM images WHERE id=?",(image_id,)).fetchone()
        if not row: return error_response("图片不存在",404)
        path=Path(row[0])
        if not path.is_absolute(): path=self.service.store.images/path.name
        path=path.resolve()
        if self.service.store.images.resolve() not in path.parents or not path.is_file(): return error_response("图片路径非法",404)
        encoded=base64.b64encode(path.read_bytes()).decode("ascii")
        return json_response({"data_url":f"data:{row[1] or 'application/octet-stream'};base64,{encoded}"})

    async def api_image_tags(self, image_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        image_id=self._positive_id(image_id)
        if image_id is None: return error_response("图片 ID 非法",400)
        data=self._json_object(await request.json(default={}))
        if data is None: return error_response("请求体必须是 JSON 对象",400)
        try:
            raw_tag_ids=data.get("tag_ids",[])
            if not isinstance(raw_tag_ids,list): raise ValueError("tag_ids 必须是数组")
            tag_ids=[int(x) for x in raw_tag_ids]
            self.service.db.update_image(image_id,tag_ids,data.get("content_description", ""))
        except Exception as exc: return error_response(str(exc),400)
        return json_response({"ok":True})

    async def api_create_tag(self):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        data=self._json_object(await request.json(default={}))
        if data is None: return error_response("请求体必须是 JSON 对象",400)
        try: tag_id=self.service.db.create_tag(data.get("name",""),data.get("kind",""))
        except Exception as exc: return error_response(str(exc),400)
        return json_response({"id":tag_id}, status_code=201)

    async def api_update_tag(self, tag_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        tag_id=self._positive_id(tag_id)
        if tag_id is None: return error_response("标签 ID 非法",400)
        data=self._json_object(await request.json(default={}))
        if data is None: return error_response("请求体必须是 JSON 对象",400)
        try: self.service.db.rename_tag(tag_id,data.get("name",""))
        except Exception as exc: return error_response(str(exc),400)
        return json_response({"ok":True})

    async def api_delete_tag(self, tag_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        tag_id=self._positive_id(tag_id)
        if tag_id is None: return error_response("标签 ID 非法",400)
        try: self.service.db.delete_tag(tag_id)
        except Exception as exc: return error_response(str(exc),409)
        return json_response({"ok":True})

    async def api_image_enabled(self, image_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        image_id=self._positive_id(image_id)
        if image_id is None: return error_response("图片 ID 非法",400)
        data=self._json_object(await request.json(default={}))
        if data is None or not isinstance(data.get("enabled"),bool): return error_response("enabled 必须是布尔值",400)
        with self.service.db.connect() as c:
            if not c.execute("SELECT 1 FROM images WHERE id=?",(image_id,)).fetchone(): return error_response("图片不存在",404)
        self.service.db.set_image_enabled(image_id,data["enabled"])
        return json_response({"ok":True})

    async def api_images_batch_enabled(self):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        data=self._json_object(await request.json(default={}))
        if data is None or not isinstance(data.get("enabled"),bool): return error_response("请求体或 enabled 非法",400)
        try:
            ids=data.get("image_ids",[])
            if not isinstance(ids,list): raise ValueError("image_ids 必须是数组")
            ids=[self._positive_id(x) for x in ids]
            if any(x is None for x in ids): raise ValueError("image_ids 含非法 ID")
            self.service.db.set_images_enabled(ids,data["enabled"])
        except Exception as exc: return error_response(str(exc),400)
        return json_response({"ok":True})

    async def api_delete_image(self, image_id):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        image_id=self._positive_id(image_id)
        if image_id is None: return error_response("图片 ID 非法",400)
        path=self.service.db.delete_image(image_id)
        if path is None: return error_response("图片不存在",404)
        if path:
            p=resolve_image_path(path,self.service.store.images)
            if p: p.unlink(missing_ok=True)
        return json_response({"ok":True})

    async def api_images_batch_delete(self):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        data=self._json_object(await request.json(default={}))
        if data is None: return error_response("请求体必须是 JSON 对象",400)
        try:
            ids=data.get("image_ids",[])
            if not isinstance(ids,list): raise ValueError("image_ids 必须是数组")
            ids=[self._positive_id(x) for x in ids]
            if any(x is None for x in ids): raise ValueError("image_ids 含非法 ID")
            paths=self.service.db.delete_images(ids)
        except Exception as exc: return error_response(str(exc),400)
        root=self.service.store.images.resolve()
        for path in paths:
            p=Path(path)
            if not p.is_absolute(): p=self.service.store.images/p.name
            p=p.resolve()
            if root in p.parents: p.unlink(missing_ok=True)
        return json_response({"ok":True,"deleted":len(paths)})

    async def api_upload(self):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        files=await request.files()
        upload=files.get("file")
        if not upload: return error_response("缺少 file",400)
        original=getattr(upload,"filename","") or "upload.png"
        try:
            with tempfile.NamedTemporaryFile() as temp:
                await upload.save(temp.name)
                data=Path(temp.name).read_bytes()
            stored=self.service.store.save(data,original)
        except Exception as exc:
            if 'stored' in locals(): Path(stored.path).unlink(missing_ok=True)
            return error_response(str(exc),400)
        return json_response({"token":stored.stored_filename,"filename":original}, status_code=201)

    async def api_upload_commit(self):
        if not self._admin_required(): return error_response("需要管理员登录",403)
        data=self._json_object(await request.json(default={}))
        if data is None: return error_response("请求体必须是 JSON 对象",400)
        try:
            raw_tag_ids=data.get("tag_ids",[])
            if not isinstance(raw_tag_ids,list): raise ValueError("tag_ids 必须是数组")
            tag_ids=[int(x) for x in raw_tag_ids]
        except (TypeError,ValueError) as exc: return error_response(str(exc),400)
        token=str(data.get("token", "")); original=str(data.get("filename", "")) or token; description=str(data.get("content_description", "")).strip()
        safe=Path(token).name
        if not token or safe != token or Path(token).suffix.lower() not in self.service.store.ALLOWED: return error_response("上传令牌非法",400)
        path=(self.service.store.images/safe).resolve()
        if self.service.store.images.resolve() not in path.parents or not path.is_file(): return error_response("上传文件不存在或已过期",404)
        try:
            import hashlib
            image_id=self.service.db.create_image_with_tags(safe,safe,tag_ids,True,self.service.store.ALLOWED[path.suffix.lower()],path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest(),description,original_filename=original)
        except Exception as exc:
            self.service.db.delete_image(image_id) if 'image_id' in locals() else None
            path.unlink(missing_ok=True)
            return error_response(str(exc),400)
        return json_response({"id":image_id,"filename":safe}, status_code=201)

    @filter.on_decorating_result(priority=99999)
    async def prepare_meme(self, event: AstrMessageEvent):
        if not bool(self.config.get("enabled",False)): return
        if self._is_plugin_llm_result(event): return
        if event.get_extra("smart_meme_processed",False): return
        event.set_extra("smart_meme_processed",True)
        result=event.get_result()
        if not result or not getattr(result,"chain",None): return
        is_llm=getattr(result,"is_llm_result",None)
        if callable(is_llm) and not is_llm(): return
        answer=self._chain_text(result.chain)
        question=getattr(event,"message_str","")
        hit=probability_hit(self.config.get("probability",50))
        event.set_extra("smart_meme_probability_hit",hit)
        logger.info("智能表情包概率命中=%s",hit)
        if not hit: return
        tags=self.service.db.list_tags('emotion')
        descriptions={x["content_description"] for x in self.service.db.list_images(True) if x["content_description"]}
        emotion,content=keyword_match(question,answer,[(x["id"],x["name"],x["kind"]) for x in tags],descriptions)
        logger.info("智能表情包关键词结果 emotion=%s content=%s",emotion,content)
        if not (emotion and content):
            try:
                selected=await asyncio.wait_for(self.service.classify(event,question,answer,emotion,content),timeout=30)
                if not selected:
                    logger.warning("智能表情包分类未得到合法情绪-内容组合 emotion=%s content=%s",emotion,content)
                    return
                emotion,content=selected["emotion"],selected["content"]
                logger.info("智能表情包 LLM 结果 emotion=%s content=%s",emotion,content)
            except Exception:
                logger.exception("智能表情包 LLM 分类失败")
                return
        candidates=self.service.db.matching_images(emotion,content)
        logger.info("智能表情包候选图片数量=%d emotion=%s content=%s",len(candidates),emotion,content)
        image=self.service.select(emotion,content)
        if not image:
            logger.warning("智能表情包匹配结果为空 emotion=%s content=%s",emotion,content)
            return
        event.set_extra("smart_meme_pending_image", image)
        event.set_extra("smart_meme_selected_image_id", image["id"])
        logger.info("智能表情包选择图片 id=%s",image["id"])

    @filter.after_message_sent()
    async def send_meme_after_text(self, event: AstrMessageEvent):
        image=event.get_extra("smart_meme_pending_image")
        if not image or event.get_extra("smart_meme_send_attempted",False): return
        event.set_extra("smart_meme_send_attempted",True)
        try:
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Image
            path=Path(image["path"])
            if not path.is_absolute(): path=self.service.store.images/path.name
            path=path.resolve()
            if self.service.store.images.resolve() not in path.parents or not path.is_file():
                logger.error("智能表情包图片路径无效 image_id=%s path=%s",image.get("id"),path)
                return
            logger.info("智能表情包准备发送 image_id=%s path=%s",image.get("id"),path)
            await self.context.send_message(event.unified_msg_origin, MessageChain([Image.fromFileSystem(str(path))]))
            logger.info("智能表情包发送成功 image_id=%s",image.get("id"))
        except Exception:
            logger.exception("智能表情包发送失败 image_id=%s",image.get("id"))

    @staticmethod
    def _chain_text(chain):
        if isinstance(chain,str): return chain
        parts=[]
        for item in chain if isinstance(chain,(list,tuple)) else [chain]:
            text=getattr(item,"text",None)
            if text: parts.append(text)
        return "".join(parts)

    async def terminate(self):
        pass
