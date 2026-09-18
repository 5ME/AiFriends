"""删除音色：先删阿里云侧，成功才删本地行。

顺序很重要：只删本地行会让**账号级**的 1000 个音色配额只增不减（阿里云不自动淘汰最早的），
而"先删本地再补删"会在网络失败时静默泄漏配额、且丢掉 `voice_id` 再也补不回来。
"""
import logging
import os

from django.db.models import RestrictedError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Character, Voice
from web.views.create.character.voice.visibility import is_voice_owned_by

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5
# Task 1 实测：对不存在的 id 调 delete_voice 返回 HTTP 400 + 这个 code
NOT_FOUND_CODE = 'BadRequest.ResourceNotExist'
NOT_FOUND_MESSAGE = '音色不存在或无权访问'          # 与 clone/create/update/sample 逐字相同


class AliyunNotFound(Exception):
    """阿里云侧已经没有这个音色（含被"1 年未使用"规则自动清理）→ 视为删除成功。"""


class AliyunUnavailable(Exception):
    """上游不可用或超时 → 503 且**保留本地行**。"""


def delete_voice(voice_id):
    """调 voice-enrollment 的 delete_voice。5 秒超时。"""
    import requests

    try:
        resp = requests.post(
            os.getenv('VOICE_URL'),
            headers={'Authorization': f'Bearer {os.getenv("API_KEY")}'},
            json={'model': 'voice-enrollment',
                  'input': {'action': 'delete_voice', 'voice_id': voice_id}},
            timeout=REQUEST_TIMEOUT)
    except Exception as e:
        raise AliyunUnavailable(str(e)) from e
    if resp.status_code == 200:
        return
    code = ''
    try:
        code = (resp.json() or {}).get('code', '')
    except Exception:
        pass
    if code == NOT_FOUND_CODE:
        raise AliyunNotFound(code)
    # ⚠️ 上游拒绝不是用户的错，不能归 400 —— 只有两档：不存在=成功，其余=503
    raise AliyunUnavailable(f'{resp.status_code} {code}'[:200])


class RemoveVoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            voice_pk = request.data.get('voice')
            try:
                voice = Voice.objects.get(id=voice_pk)
            except (Voice.DoesNotExist, ValueError, TypeError):
                return Response({'message': NOT_FOUND_MESSAGE},
                                status=status.HTTP_404_NOT_FOUND)
            if not is_voice_owned_by(voice, request.user.userprofile):
                # ⚠️ 必须校验**归属**而不是可见性：可见性对平台音色恒为真，
                # 用可见性做准入 = 任何登录用户都能删平台音色（spec §5：只能删自己的）。
                # message 与上面的"不存在"逐字相同 —— 否则 404 就成了存在性探测器。
                return Response({'message': NOT_FOUND_MESSAGE},
                                status=status.HTTP_404_NOT_FOUND)

            in_use = Character.objects.filter(voice=voice).count()
            if in_use:
                return Response({'message': f'该音色正被 {in_use} 个角色使用，无法删除'},
                                status=status.HTTP_400_BAD_REQUEST)

            try:
                delete_voice(voice.voice_id)
            except AliyunNotFound:
                logger.info('阿里云侧已不存在，视为删除成功: voice=%s', voice.id)
            except Exception as e:
                logger.exception('删除阿里云侧音色失败，保留本地行: voice=%s', voice.id)
                return Response({'message': '删除失败，请稍后重试'},
                                status=status.HTTP_503_SERVICE_UNAVAILABLE)

            try:
                voice.delete()
            except RestrictedError:
                # 预检查与真正删除之间的竞态（这中间新建了一个用它的角色）——
                # 不补这层，RestrictedError 会漏到最外面变成 500（spec §7 明确不许）
                n = Character.objects.filter(voice_id=voice_pk).count()
                return Response({'message': f'该音色正被 {n} 个角色使用，无法删除'},
                                status=status.HTTP_400_BAD_REQUEST)
            return Response({'message': 'success'})
        except Exception as e:
            logger.exception('删除音色异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
