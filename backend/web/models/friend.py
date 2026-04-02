from django.db import models
from django.utils.timezone import now, localtime

from web.models.character import Character
from web.models.user import UserProfile


class Friend(models.Model):
    """
    用户与角色的好友关系
    """
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    character = models.ForeignKey(Character, on_delete=models.CASCADE)
    memory = models.TextField(default='', max_length=5000, blank=True, null=True)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(default=now)

    def __str__(self):
        return f'{self.character.name} - {self.user_profile.user.username} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'


class Message(models.Model):
    """
    用户与角色的聊天信息
    """
    # 好友关系
    friend = models.ForeignKey(Friend, on_delete=models.CASCADE)
    user_message = models.TextField(max_length=5000)
    input = models.TextField(max_length=5000)
    output = models.TextField(max_length=5000)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=now)

    def __str__(self):
        return f'{self.friend.character.name} - {self.friend.user_profile.user.username} - {self.user_message[:50]} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'
