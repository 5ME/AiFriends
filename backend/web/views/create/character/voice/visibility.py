"""音色可见性规则 —— 只在这里定义一次。

列表（get_list）、详情（get_single）、选角（create / update）、试听（sample）
四处共用同一个 Q，避免"改了列表忘了校验"这类漏洞。
"""
from django.db.models import Q

from web.models.character import Voice


def visibility_q(profile):
    return Q(visibility='public') | Q(owner=profile)


def visible_voices(profile):
    return Voice.objects.filter(visibility_q(profile)).order_by('id')


def is_voice_visible(voice, profile):
    return Voice.objects.filter(visibility_q(profile), pk=voice.pk).exists()
