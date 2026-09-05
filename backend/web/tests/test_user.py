from web.models.user import DEFAULT_PHOTO


def test_photo_url_default_returns_static(user_profile):
    """默认头像（未上传自定义照片）→ 返回 static URL 而非 media URL"""
    assert user_profile.photo.name == DEFAULT_PHOTO
    assert user_profile.photo_url == '/static/frontend/default.png'
