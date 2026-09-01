import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now, localtime

DEFAULT_PHOTO = 'user/photos/default.png'


def photo_upload_to(instance, filename):
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4().hex[:16]}.{ext}'
    return f'user/photos/{instance.user_id}_{filename}'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    photo = models.ImageField(default=DEFAULT_PHOTO, upload_to=photo_upload_to)
    profile = models.TextField(default='谢谢你的关注', max_length=500)
    created_at = models.DateTimeField(default=now)
    updated_at = models.DateTimeField(default=now)

    @property
    def photo_url(self):
        if self.photo and self.photo.name != DEFAULT_PHOTO:
            return self.photo.url
        return settings.STATIC_URL + 'frontend/default.png'

    def __str__(self):
        return f'{self.user.username} - {localtime(self.created_at).strftime("%Y-%m-%d %H:%M:%S")}'
