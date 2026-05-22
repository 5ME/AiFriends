from django.db import models
from django.utils.timezone import now, localtime

from web.models.character import Character
from web.models.user import UserProfile


class Friend(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    character = models.ForeignKey(Character, on_delete=models.CASCADE)
    memory = models.TextField(default='', max_length=5000, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['user_profile', 'character']]
        indexes = [models.Index(fields=['user_profile'])]

    def __str__(self):
        return f'{self.character.name} - {self.user_profile.user.username} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'


class Message(models.Model):
    friend = models.ForeignKey(Friend, on_delete=models.CASCADE)
    user_message = models.TextField(max_length=5000)
    input = models.JSONField(max_length=50000, default=dict)
    output = models.TextField(max_length=5000)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['friend', '-created_at'])]

    def __str__(self):
        return f'{self.friend.character.name} - {self.friend.user_profile.user.username} - {self.user_message[:50]} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'


class SystemPrompt(models.Model):
    class Title(models.TextChoices):
        REPLY = 'reply', '回复'
        MEMORY = 'memory', '记忆'

    title = models.CharField(max_length=20, choices=Title.choices)
    order_number = models.IntegerField(default=0)
    prompt = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} - {self.order_number} - {self.prompt[:50]} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'
