from __future__ import annotations
import random

def probability_hit(value, roll=None):
    value=max(0,min(100,int(value)))
    return (random.randint(1,100) if roll is None else roll) <= value

def keyword_match(question, answer, emotion_tags, content_descriptions=()):
    text=f"{question or ''}{answer or ''}"
    found_emotion=None; found_content=None; emotion_pos=len(text)+1; content_pos=len(text)+1
    for _id,name,_kind in emotion_tags:
        pos=text.find(name) if name else -1
        if 0 <= pos < emotion_pos: emotion_pos,found_emotion=pos,name
    for description in content_descriptions:
        pos=text.find(description) if description else -1
        if 0 <= pos < content_pos: content_pos,found_content=pos,description
    return found_emotion, found_content

def choose_image(images):
    return random.choice(images) if images else None
