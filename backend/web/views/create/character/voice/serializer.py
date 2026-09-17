def serialize_voice(voice, profile):
    """音色对外表示。get_list / get_single 共用一份，避免改一处漏一处。

    `is_mine` 只对"用户自建且属于调用者"为真；平台音色（`owner` 为空）恒为假。
    """
    return {
        'id': voice.id,
        'name': voice.name,
        'profile': voice.profile,
        'status': voice.status,
        'is_mine': voice.owner_id is not None and voice.owner_id == profile.id,
    }
