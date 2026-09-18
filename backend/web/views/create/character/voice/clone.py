"""音色复刻：上传样本 → OSS(对象级 private) → 签名 URL → 阿里云 create_voice。

铁律：样本**无论成败都立即删除**；同步失败**不建行**（拿不到阿里云 id 时硬塞一行等于让字段说谎）。
"""
import logging
import os
import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.models.character import Voice
from web.utils.oss import (OssConfigError, delete_object_quietly, presign_get,
                           upload_private)
from web.views.create.character.voice.visibility import (VOICE_QUOTA_PER_USER,
                                                         user_voice_count)

logger = logging.getLogger(__name__)

MAX_SAMPLE_BYTES = 8 * 1024 * 1024          # nginx client_max_body_size 是 10m，留出 multipart 余量
ALLOWED_SUFFIXES = {'mp3', 'wav', 'm4a'}
NAME_MAX_LEN = 100                          # 与 Voice.name 的 max_length 对齐
PROFILE_MAX_LEN = 500
REQUEST_TIMEOUT = 5
CONSENT_TRUE = {'true', '1', 'on', 'yes'}


def looks_like_audio(data: bytes, suffix: str) -> bool:
    """magic byte 校验（spec §6.2.3）。

    ⚠️ 不能照搬 `views/document/upload.py:21` 那张 MAGIC_BYTES 表：它里面**没有音频项**，
    而且 m4a 的 `ftyp` 在**第 4 字节**而不是开头 —— 所以这里单独写一个。
    """
    if suffix == 'mp3':
        # 有 ID3 头就收；否则看**帧同步**：0xFF 后高 3 位全 1 —— 位掩码一次覆盖
        # \xff\xfb / \xff\xfa / \xff\xf3 / \xff\xf2 / \xff\xe3 / \xff\xe2，
        # 而枚举字节对会漏（\xff\xfa 是带 CRC 的 MPEG-1 Layer III，实际文件里常见）。
        # 方向也重要：误拒合法文件比误收更糟（误收最多被阿里云拒一次）。
        return data[:3] == b'ID3' or (len(data) > 1 and data[0] == 0xFF
                                      and (data[1] & 0xE0) == 0xE0)
    if suffix == 'wav':
        return data[:4] == b'RIFF'
    if suffix == 'm4a':
        return data[4:8] == b'ftyp'
    return False


class AliyunRejected(Exception):
    """阿里云**明确拒绝**（样本不合格 / 敏感内容 / 账号配额耗尽 / 2038 无复刻权限）→ 400。"""


class AliyunUnavailable(Exception):
    """上游不可用或超时 → 503。"""


def create_voice(url, prefix):
    """调 voice-enrollment 的 create_voice。5 秒超时。"""
    import requests

    payload = {'model': 'voice-enrollment', 'input': {
        'action': 'create_voice', 'target_model': 'cosyvoice-v3-flash',
        'prefix': prefix, 'url': url}}
    try:
        resp = requests.post(
            os.getenv('VOICE_URL'),
            headers={'Authorization': f'Bearer {os.getenv("API_KEY")}'},
            json=payload, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        raise AliyunUnavailable(str(e)) from e
    data = resp.json() if resp.content else {}
    out = data.get('output') or {}
    if resp.status_code != 200 or not out.get('voice_id'):
        raise AliyunRejected(
            f'{resp.status_code} {data.get("code", "")} {data.get("message", "")}'[:300])
    return out['voice_id']


class CloneVoiceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sample = request.FILES.get('file')
        name = (request.data.get('name') or '').strip()
        profile = (request.data.get('profile') or '').strip()
        consent = str(request.data.get('consent', '')).lower()

        if not name or len(name) > NAME_MAX_LEN:
            return Response({'message': f'音色名称必填且不超过 {NAME_MAX_LEN} 字'},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(profile) > PROFILE_MAX_LEN:
            return Response({'message': f'音色描述不超过 {PROFILE_MAX_LEN} 字'},
                            status=status.HTTP_400_BAD_REQUEST)
        if consent not in CONSENT_TRUE:
            # spec §6.2.1 / §8：样本是用户的声音，必须先拿到授权声明（后端也要挡，不只靠前端）
            return Response({'message': '请先确认授权声明：这是本人声音，或已获得声音权利人授权'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not sample:
            return Response({'message': '请上传声音样本'},
                            status=status.HTTP_400_BAD_REQUEST)
        if sample.size > MAX_SAMPLE_BYTES:
            return Response({'message': f'样本不得超过 {MAX_SAMPLE_BYTES // 1024 // 1024}MB'},
                            status=status.HTTP_400_BAD_REQUEST)
        suffix = (sample.name.rsplit('.', 1)[-1] if '.' in sample.name else '').lower()
        if suffix not in ALLOWED_SUFFIXES:
            return Response({'message': '样本格式只支持 mp3 / wav / m4a'},
                            status=status.HTTP_400_BAD_REQUEST)
        data = sample.read()
        if not looks_like_audio(data, suffix):
            return Response({'message': '样本内容不是有效的音频文件'},
                            status=status.HTTP_400_BAD_REQUEST)

        profile_obj = request.user.userprofile
        if user_voice_count(profile_obj) >= VOICE_QUOTA_PER_USER:
            return Response({'message': f'最多只能创建 {VOICE_QUOTA_PER_USER} 个音色'},
                            status=status.HTTP_400_BAD_REQUEST)

        key = None
        try:
            key = upload_private(data, suffix)
            url = presign_get(key)                       # 5 分钟有效
            prefix = f'vf{profile_obj.id}{uuid.uuid4().hex[:4]}'   # 字母数字、≤10
            logger.info('复刻请求: consent=true user=%s name=%s prefix=%s',
                        profile_obj.id, name, prefix)
            voice_id = create_voice(url, prefix)
        except OssConfigError as e:
            # OSS 配置/凭据/权限错 —— 不是用户的错，也不是上游抖动，归 500 给运维（spec §7 两档分开）
            logger.error('OSS 配置错误，复刻不可用: %s', e)
            return Response({'message': '复刻服务未正确配置，请联系管理员'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except AliyunRejected as e:
            # 措辞刻意**不断言"样本有问题"**：账号配额耗尽、上游策略变化等也会走到这里，
            # 把上游原文带上（含 code），日志里留全量
            logger.warning('复刻被阿里云拒绝: %s', e)
            return Response({'message': f'复刻未成功（上游拒绝：{e}）'},
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('复刻失败（上游不可用）: %s', e)
            return Response({'message': '复刻服务暂时不可用，请稍后再试'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        finally:
            if key:
                delete_object_quietly(key)               # 无论成败都删样本

        voice = Voice.objects.create(name=name, voice_id=voice_id, profile=profile,
                                     owner=profile_obj, visibility='private',
                                     status='deploying')
        return Response({'message': 'success',
                         'voice': {'id': voice.id, 'status': voice.status}})
