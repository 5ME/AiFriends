import os

from django.conf import settings

DEFAULT_PHOTO = 'user/photos/default.png'


def remove_old_photo(photo) -> None:
    if photo and photo.name != DEFAULT_PHOTO:
        old_photo_path = settings.MEDIA_ROOT / photo.name
        if old_photo_path.exists():
            os.remove(old_photo_path)
