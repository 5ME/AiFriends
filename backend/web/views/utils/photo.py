import os

from django.conf import settings

DEFAULT_PHOTO = 'user/photos/default.png'


def remove_old_photo(photo) -> None:
    if photo and photo != DEFAULT_PHOTO:
        old_photo_path = settings.MEDIA_ROOT / photo
        if old_photo_path.exists():
            os.remove(old_photo_path)
