from django.db.models import Max
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.friend import Friend


class FriendGetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            friends_raw = Friend.objects.filter(user_profile__user=request.user) \
                              .annotate(last_active=Coalesce(Max('message__created_at'), 'created_at')) \
                              .order_by('-last_active')[items_count:items_count + 20]
            friends = []
            for friend in friends_raw:
                character = friend.character
                author = character.author
                friends.append({
                    'id': friend.id,
                    'character': {
                        'id': character.id,
                        'name': character.name,
                        'profile': character.profile,
                        'photo': character.photo.url,
                        'background_image': character.background_image.url,
                        'author': {
                            'user_id': author.user_id,
                            'username': author.user.username,
                            'photo': author.photo.url,
                        }
                    }
                })
            return Response({'message': 'success', 'friends': friends})
        except:
            return Response({'message': '系统错误'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
