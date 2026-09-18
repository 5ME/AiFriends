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


def is_voice_owned_by(voice, profile):
    """归属判定 —— 与可见性是两码事，别混用。

    `is_voice_visible` 对**平台音色**（`owner=None` + `public`）恒为真，所以拿它当"能否删除"的
    准入条件 = 任何登录用户都能删掉龙安洋 / 龙安欢 / 管理员手工录入的音色。删除只认归属。
    """
    return voice.owner_id is not None and voice.owner_id == profile.id


VOICE_QUOTA_PER_USER = 5
USER_VOICE_COUNT_WARN = 800       # 全平台水位告警（1000 是账号级上限）


def user_voice_count(profile):
    return Voice.objects.filter(owner=profile).count()
