import hashlib
import logging
import re
import time
from pathlib import Path

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice
from web.utils.tts import TTS_MODEL, synthesize_once
from web.utils.usage import record_api_usage
from web.views.create.character.voice.visibility import is_voice_visible

logger = logging.getLogger(__name__)

SAMPLE_TEXT_TEMPLATE = '你好呀，我是{}，很高兴认识你。'
SAMPLE_NAME_MAX_LEN = 20          # 音色名会被拼进 TTS 文案，截断防止成本随用户输入膨胀
NEGATIVE_CACHE_SECONDS = 60       # 失败后在窗口内不再打上游
SAMPLE_DIR_NAME = 'voice_samples'


def build_sample_text(voice_name):
    return SAMPLE_TEXT_TEMPLATE.format((voice_name or '')[:SAMPLE_NAME_MAX_LEN])


def _sample_dir():
    return Path(settings.MEDIA_ROOT) / SAMPLE_DIR_NAME


UNSAFE_VOICE_ID_CHARS = re.compile(r'[^A-Za-z0-9_-]')


def sample_cache_path(voice_id, text):
    """缓存键 = 阿里云音色标识 + 样本文案 hash（文案变了就换文件名，避免被浏览器缓存误导）。

    阿里云标识要先剥掉非法字符再入文件名：校验器只挡得住经表单的未来写入、不回溯存量行，
    而 `Path('a') / '../../evil-x.mp3'` 是纯词法拼接，会真的写到缓存目录之外。
    """
    safe_id = UNSAFE_VOICE_ID_CHARS.sub('', voice_id or '')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]
    return _sample_dir() / f'{safe_id}-{digest}.mp3'


def _negative_cache_active(path):
    marker = path.with_suffix(path.suffix + '.fail')
    return marker.exists() and (time.time() - marker.stat().st_mtime) < NEGATIVE_CACHE_SECONDS


def _touch_negative_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(path.suffix + '.fail').write_text('', encoding='utf-8')


class GetVoiceSampleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            voice_id = request.query_params.get('voice')
            try:
                voice = Voice.objects.get(id=voice_id)
            except (Voice.DoesNotExist, ValueError, TypeError):
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            if not is_voice_visible(voice, request.user.userprofile):
                # message 必须与上面的"不存在"逐字相同 —— 否则 404 就成了存在性探测器
                return Response({'message': '音色不存在或无权访问'},
                                status=status.HTTP_404_NOT_FOUND)
            if voice.status != 'ready':
                # 没就绪就不该去打阿里云：既花钱又慢
                return Response({'message': '该音色尚不可用（审核中 / 审核未通过）'},
                                status=status.HTTP_400_BAD_REQUEST)

            text = build_sample_text(voice.name)
            path = sample_cache_path(voice.voice_id, text)
            if not path.exists():
                if _negative_cache_active(path):
                    return Response({'message': '样音暂时无法生成，请稍后再试'},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
                try:
                    audio = synthesize_once(text, voice.voice_id)
                except Exception as e:
                    logger.exception('样音合成失败: voice=%s', voice.id)
                    _touch_negative_cache(path)
                    # UserProfile.id 而非 User.id —— APIUsage.user 是 UserProfile 的 FK
                    record_api_usage(user_id=request.user.userprofile.id, api_type='tts',
                                     model_name=TTS_MODEL, success=False,
                                     error_message=str(e)[:500], update_quota=False)
                    return Response({'message': '样音暂时无法生成，请稍后再试'},
                                    status=status.HTTP_503_SERVICE_UNAVAILABLE)
                _sample_dir().mkdir(parents=True, exist_ok=True)
                path.write_bytes(audio)
                # UserProfile.id 而非 User.id —— APIUsage.user 是 UserProfile 的 FK
                record_api_usage(user_id=request.user.userprofile.id, api_type='tts',
                                 model_name=TTS_MODEL, token_count=len(text),
                                 success=True, update_quota=False)

            return Response({'message': 'success',
                             'url': f'{settings.MEDIA_URL}{SAMPLE_DIR_NAME}/{path.name}'})
        except Exception as e:
            logger.exception('获取样音异常: %s', e)
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
