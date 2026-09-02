import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from backend.database import Database


def test_active_emotion_tags_exclude_disabled_only_tags(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    active=db.create_tag('有效'); disabled=db.create_tag('禁用')
    i1=db.create_image('a.png','a.png',True,content_description='猫咪'); i2=db.create_image('b.png','b.png',False,content_description='狗狗')
    db.attach_tag(i1,active); db.attach_tag(i2,disabled)
    assert [x['name'] for x in db.active_tags('emotion')] == ['有效']


def test_content_description_is_per_image_and_editable(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    emotion=db.create_tag('开心')
    image=db.create_image('a.png','a.png',content_description='猫咪趴着')
    db.attach_tag(image,emotion)
    db.update_image(image,[emotion],'猫咪看着镜头')
    row=db.list_images()[0]
    assert row['content_description']=='猫咪看着镜头'
    assert row['emotion_tags']==['开心']


def test_content_tags_are_not_global(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    assert db.list_tags('content') == []
    try:
        db.create_tag('猫咪','content')
    except ValueError:
        pass
    else:
        raise AssertionError('content tags must not be created')


def test_create_image_with_tags_commits_image_and_relations_atomically(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    emotion=db.create_tag('开心')
    image=db.create_image_with_tags('a.png','a.png',[emotion],content_description='猫咪挥手')
    row=db.list_images()[0]
    assert image == row['id']
    assert row['emotion_tags'] == ['开心']


def test_create_image_with_tags_rejects_invalid_tag_without_image(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    try:
        db.create_image_with_tags('a.png','a.png',[999],content_description='无效标签')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid tag was accepted')
    assert db.list_images() == []
