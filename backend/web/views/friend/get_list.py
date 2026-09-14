from django.db.models import Max, OuterRef, Subquery
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import logging

from web.models.friend import Friend, Message

logger = logging.getLogger(__name__)

# 会话栏预览最大长度：前端单行截断显示，长文本不整条回传
PREVIEW_MAX_LEN = 60


class FriendGetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            # 会话栏预览：最后一条消息，按 created_at/-id 取（与排序键 last_active 同源）
            last_message = Message.objects.filter(friend=OuterRef('pk')) \
                                          .order_by('-created_at', '-id')
            # select_related 一次性 JOIN character→author→user，避免循环中逐条查 3 次
            friends_raw = Friend.objects.filter(user_profile__user=request.user) \
                              .select_related('character__author__user') \
                              .annotate(
                                  last_active=Coalesce(Max('message__created_at'), 'created_at'),
                                  last_output=Subquery(last_message.values('output')[:1]),
                                  last_user_message=Subquery(
                                      last_message.values('user_message')[:1]),
                                  last_message_at=Subquery(
                                      last_message.values('created_at')[:1]),
                              ) \
                              .order_by('-last_active')[items_count:items_count + 20]
            friends = []
            for friend in friends_raw:
                # output 为空/全空白（流中断/模型空回复）回退 user_message；
                # 空白归一化 + 截断，避免 20 条 × 5000 字符的 payload
                preview = (friend.last_output or '').strip() \
                    or (friend.last_user_message or '').strip()
                friends.append({
                    'id': friend.id,
                    'last_message': ' '.join(preview.split())[:PREVIEW_MAX_LEN],
                    'last_message_at': friend.last_message_at.isoformat()
                                       if friend.last_message_at else None,
                    'character': {
                        'id': friend.character_id,
                        'name': friend.character.name,
                        'introduction': friend.character.introduction,
                        'photo': friend.character.photo_url,
                        'background_image': friend.character.background_image_url,
                        'author': {
                            'user_id': friend.character.author.user_id,
                            'username': friend.character.author.user.username,
                            'photo': friend.character.author.photo_url,
                        }
                    }
                })
            return Response({'message': 'success', 'friends': friends})
        except Exception as e:
            logger.exception('获取好友列表异常: %s', e)
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
