from __future__ import annotations
import json
import logging
from .database import Database
from .image_store import ImageStore
from .llm_classifier import build_prompt, parse_selection
from .matching import choose_image, keyword_match, probability_hit

logger = logging.getLogger("astrbot_plugin_smart_meme.classifier")

class SmartMemeService:
    def __init__(self, data_dir, config=None):
        config=config or {}; self.data_dir=data_dir
        self.db=Database(data_dir / "database.sqlite3")
        self.store=ImageStore(data_dir, int(config.get("max_upload_size_mb",config.get("max_image_size_mb",10)))*1024*1024)
        self.config=config
    async def classify(self, event, question, answer, emotion, content):
        tags=self.db.active_tags('emotion'); pairs=self.db.active_image_pairs()
        if emotion: pairs=[pair for pair in pairs if pair[0] == emotion]
        if content: pairs=[pair for pair in pairs if pair[1] == content]
        missing=set()
        if not emotion: missing.add("emotion")
        if not content: missing.add("content")
        logger.info("分类候选真实组合数量=%d emotion=%s content=%s missing=%s",len(pairs),emotion,content,sorted(missing))
        if not pairs:
            logger.warning("分类候选真实组合为空 emotion=%s content=%s",emotion,content)
            return None
        allowed={"emotion":{e for e,_ in pairs},"content":{c for _,c in pairs}}
        if missing == {"content"}:
            pass
        elif missing == {"emotion"}:
            pass
        prompt=build_prompt(question,answer,sorted(allowed["emotion"]),sorted(allowed["content"]),missing,pairs)
        provider=await self.context_provider(event)
        if not provider: return None
        retries=max(0,int(self.config.get("llm_retry_count",self.config.get("llm_retries",0))))
        for attempt in range(1,retries+2):
            try:
                logger.info("分类请求开始 attempt=%d/%d provider=%s missing=%s",attempt,retries+1,provider,sorted(missing))
                response=await self.context.llm_generate(chat_provider_id=provider,prompt=prompt)
                raw=str(getattr(response,"completion_text","") or "")
                parsed=parse_selection(raw,allowed,missing,set(pairs))
                logger.info("分类原始返回 attempt=%d text=%s",attempt,raw[:2000].replace("\n","\\n"))
                logger.info("分类校验结果 attempt=%d valid=%s parsed=%s",attempt,bool(parsed),parsed)
                if parsed:
                    result={"emotion": emotion or parsed.get("emotion"), "content": content or parsed.get("content")}
                    logger.info("分类成功 attempt=%d result=%s",attempt,result)
                    return result
                logger.warning("分类返回未通过校验 attempt=%d allowed_emotions=%d allowed_contents=%d pair_count=%d",attempt,len(allowed["emotion"]),len(allowed["content"]),len(pairs))
            except Exception:
                logger.exception("分类请求异常 attempt=%d/%d",attempt,retries+1)
        logger.warning("分类最终失败 attempts=%d",retries+1)
        return None
    async def context_provider(self,event):
        return await self.context.get_current_chat_provider_id(event.unified_msg_origin)
    def select(self, emotion, content): return choose_image(self.db.matching_images(emotion,content))
