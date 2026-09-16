def serialize_voice(voice):
    """音色对外表示。get_list / get_single 共用一份，避免改一处漏一处。"""
    return {
        'id': voice.id,
        'name': voice.name,
        'profile': voice.profile,
    }
