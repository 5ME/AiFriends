import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.utils.timezone import now, localtime

from web.models.user import UserProfile


def photo_upload_to(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4().hex[:10]}.{ext}'
    return f'character/photos/{instance.author.user_id}_{filename}'


def background_image_upload_to(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4().hex[:10]}.{ext}'
    return f'character/background_images/{instance.author.user_id}_{filename}'


VOICE_ID_VALIDATOR = RegexValidator(
    r'^[A-Za-z0-9][A-Za-z0-9_-]*$',
    '音色 ID 只能是字母、数字、下划线或连字符',
)


class Voice(models.Model):
    name = models.CharField(max_length=100)
    voice_id = models.CharField(
        max_length=100,
        help_text="阿里云音色ID",
        validators=[VOICE_ID_VALIDATOR],
    )
    profile = models.TextField(max_length=500, default='')
    is_builtin = models.BooleanField(default=False)
    owner = models.ForeignKey(UserProfile, null=True, blank=True,
                              on_delete=models.CASCADE)
    visibility = models.CharField(max_length=10, default='private',
                                  choices=[('private', '私有'), ('public', '公开')])
    status = models.CharField(max_length=12, default='ready', choices=[
        ('ready', '可用'), ('deploying', '审核中'), ('rejected', '审核未通过'),
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.voice_id} - {localtime(self.created_at).strftime('%Y-%m-%d %H:%M:%S')}"


class Character(models.Model):
    author = models.ForeignKey(UserProfile, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=50)
    introduction = models.TextField(max_length=500, default='')
    system_prompt = models.TextField(max_length=10000, default='')
    photo = models.ImageField(upload_to=photo_upload_to)
    voice = models.ForeignKey(Voice, default=None, on_delete=models.RESTRICT, blank=True, null=True)
    background_image = models.ImageField(upload_to=background_image_upload_to)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def photo_url(self):
        try:
            return self.photo.url
        except ValueError:
            return ''

    @property
    def background_image_url(self):
        try:
            return self.background_image.url
        except ValueError:
            return ''

    def __str__(self):
        return f"{self.author.user.username} - {self.name} - {localtime(self.created_at).strftime('%Y-%m-%d %H:%M:%S')}"
