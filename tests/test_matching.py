import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.matching import keyword_match, probability_hit


def test_keyword_match_uses_first_occurrence_per_dimension():
    emotions=[(1,'开心','emotion'),(2,'愤怒','emotion')]
    assert keyword_match('愤怒然后开心','猫咪太好了',emotions,['太好了']) == ('愤怒','太好了')


def test_content_description_is_selected_from_actual_images():
    emotions=[(1,'开心','emotion')]
    assert keyword_match('开心','普通回复',emotions,['猫咪看着镜头','狗狗跑步']) == ('开心',None)


def test_probability_boundaries():
    assert probability_hit(0, roll=1) is False
    assert probability_hit(100, roll=100) is True
    assert probability_hit(50, roll=50) is True
    assert probability_hit(50, roll=51) is False
