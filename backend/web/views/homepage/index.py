from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character


class HomepageIndexView(APIView):
    def get(self, request):
        try:
            items_count = int(request.query_params.get('items_count', 0))
            search_text = request.query_params.get('search_text', '').strip()
            if search_text:
                queryset = Character.objects.filter(
                    Q(name__icontains=search_text) | Q(profile__icontains=search_text)
                )
            else:
                queryset = Character.objects.all()
            characters_raw = queryset.order_by('-id')[items_count:items_count + 20]
            characters = []
            for character in characters_raw:
                author = character.author
                characters.append({
                    'id': character.id,
                    'name': character.name,
                    'profile': character.profile,
                    'photo': character.photo.url,
                    'background_image': character.background_image.url,
                    'author': {
                        'user_id': author.user_id,
                        'username': author.user.username,
                        'photo': author.photo.url
                    }
                })
            return Response({'message': 'success', 'characters': characters})
        except:
            return Response({"message": "系统异常"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
