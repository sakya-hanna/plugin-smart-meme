from __future__ import annotations
import json

def parse_selection(raw: str, allowed: dict[str, set[str]], required: set[str], valid_pairs=None):
    try:
        data=json.loads(raw)
    except Exception: return None
    if not isinstance(data, dict) or set(data) != required: return None
    if any(not isinstance(data[k], str) or not data[k].strip() or data[k] not in allowed.get(k,set()) for k in required): return None
    if valid_pairs is not None and {"emotion", "content"}.issubset(data) and (data["emotion"], data["content"]) not in valid_pairs:
        return None
    return data

def build_prompt(question, answer, emotion_tags, content_tags, missing, valid_pairs=None):
    fields=[]
    if "emotion" in missing: fields.append('"emotion": "从允许的情绪标签中选择一个"')
    if "content" in missing: fields.append('"content": "从允许的内容标签中选择一个"')
    pair_text = ""
    if valid_pairs is not None:
        pair_text = f"允许的真实情绪-内容组合（必须从同一行选择，不得自由组合）：{json.dumps([{'emotion': e, 'content': c} for e, c in valid_pairs], ensure_ascii=False)}\n"
    return ("你是表情包标签分类器。只返回严格 JSON，不要 Markdown、解释或额外字段。\n"
            f"用户问题：{question}\nAI回答：{answer}\n"
            f"允许的情绪标签：{json.dumps(emotion_tags, ensure_ascii=False)}\n"
            f"允许的内容标签：{json.dumps(content_tags, ensure_ascii=False)}\n"
            f"{pair_text}"
            f"必须返回：{{{', '.join(fields)}}}")
