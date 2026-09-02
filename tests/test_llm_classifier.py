import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.llm_classifier import parse_selection, build_prompt

def test_parse_selection_requires_whitelisted_fields():
    assert parse_selection('{"content":"太好了"}', {"content": {"太好了"}}, {"content"}) == {"content":"太好了"}

def test_parse_selection_rejects_unknown_tag_and_extra_field():
    assert parse_selection('{"content":"不存在"}', {"content": {"太好了"}}, {"content"}) is None
    assert parse_selection('{"emotion":"开心","content":"太好了"}', {"content": {"太好了"}}, {"content"}) is None

def test_parse_selection_rejects_unknown_emotion_content_pair():
    allowed={"emotion":{"开心","无奈"},"content":{"晚安捏"}}
    pairs={("开心","晚安捏")}
    assert parse_selection('{"emotion":"无奈","content":"晚安捏"}', allowed, {"emotion","content"}, pairs) is None
    assert parse_selection('{"emotion":"开心","content":"晚安捏"}', allowed, {"emotion","content"}, pairs) == {"emotion":"开心","content":"晚安捏"}

def test_build_prompt_includes_real_pairs():
    prompt=build_prompt("问题","回答",["开心"],["晚安捏"],{"emotion","content"},[("开心","晚安捏")])
    assert '不得自由组合' in prompt
    assert '"emotion": "开心"' in prompt
