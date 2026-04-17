from django.utils.timezone import now
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character, Voice
from web.models.user import UserProfile
from web.views.utils.photo import remove_old_photo


class UpdateCharacterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            character_id = request.data['character_id']
            character = Character.objects.get(id=character_id, author__user=request.user)
            name = request.data['name'].strip()
            profile = request.data['profile'].strip()
            photo = request.FILES.get('photo', None)
            background_image = request.FILES.get('background_image', None)
            voice_id = request.data['voice_id']

            if not name:
                return Response({'message': '角色名称不能为空'})
            if not profile:
                return Response({'message': '角色信息不能为空'})

            voice = Voice.objects.get(id=voice_id)
            character.voice = voice

            character.name = name
            character.profile = profile
            old_photo = None
            if photo:
                old_photo = character.photo
                character.photo = photo
            old_background_image = None
            if background_image:
                old_background_image = character.background_image
                character.background_image = background_image
            character.updated_at = now()
            character.save()

            if old_photo:
                remove_old_photo(old_photo)
            if old_background_image:
                remove_old_photo(old_background_image)

            return Response({'message': 'success'})
        except:
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
