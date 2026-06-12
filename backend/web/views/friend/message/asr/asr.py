import asyncio
import json
import os
import time
import uuid
import logging

import websockets
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from web.utils.usage import record_api_usage

logger = logging.getLogger(__name__)


class ASRView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            audio = request.FILES.get('audio')
            if not audio:
                return Response({'message': '音频不存在'},
                                status=status.HTTP_400_BAD_REQUEST)
            logger.info('ASR 开始')
            pcm_data = audio.read()
            # 在同步上下文中获取 UserProfile.id，避免 async 内触发懒加载 DB 查询
            user_id = self.request.user.userprofile.id
            text = asyncio.run(self.run_asr_task(pcm_data, user_id))
            logger.info('ASR 完成, text_length=%d', len(text))
            return Response({'message': 'success', 'text': text})
        except Exception:
            logger.exception('ASR 执行异常')
            return Response({'message': '系统异常'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def run_asr_task(self, pcm_data, user_id):
        start = time.time()
        success = True
        error_message = ''
        try:
            task_id = uuid.uuid4().hex
            wss_url = os.getenv('WSS_URL')
            api_key = os.getenv('API_KEY')
            headers = {'Authorization': f'Bearer {api_key}'}
            # 发送 run-task 指令：开启语音识别任务
            async with websockets.connect(wss_url, additional_headers=headers) as ws:
                await ws.send(json.dumps({
                    "header": {
                        "streaming": "duplex",
                        "task_id": task_id,
                        "action": "run-task"
                    },
                    "payload": {
                        "model": "gummy-realtime-v1",
                        "parameters": {
                            "sample_rate": 16000,
                            "format": "pcm",
                            "source_language": "auto",
                            "transcription_enabled": True,
                            # "translation_enabled": True,
                            # "translation_target_languages": ["en"]
                        },
                        "input": {},
                        "task": "asr",
                        "task_group": "audio",
                        "function": "recognition"
                    }
                }))
                logger.info('ASR WebSocket 已连接, task_id=%s', task_id)
                async for msg in ws:
                    if json.loads(msg)['header']['event'] == 'task-started':
                        # 收到 task-started 事件后，再发送待识别的音频流
                        break
                _, text = await asyncio.gather(
                    self.asr_sender(ws, task_id, pcm_data),
                    self.asr_receiver(ws)
                )
                return text
        except Exception as e:
            success = False
            error_message = str(e)[:500]
            raise
        finally:
            duration_ms = int((time.time() - start) * 1000)
            record_api_usage(
                user_id=user_id,
                api_type='asr',
                model_name='gummy-realtime-v1',
                token_count=len(pcm_data) // 2,  # PCM16 采样点数
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
            )

    async def asr_sender(self, ws, task_id, pcm_data):
        chunk = 3200
        # 分段发送二进制待识别音频流
        for i in range(0, len(pcm_data), chunk):
            await ws.send(pcm_data[i: i + chunk])
            await asyncio.sleep(0.01)
        # 发送 finish-task 指令：结束语音识别任务
        await ws.send(json.dumps({
            "header": {
                "action": "finish-task",
                "task_id": task_id,
                "streaming": "duplex"
            },
            "payload": {
                "input": {}
            }
        }))

    async def asr_receiver(self, ws) -> str:
        text = []
        # 持续接收服务端响应数据
        async for msg in ws:
            data = json.loads(msg)
            event = data['header']['event']
            # result-generated 事件包含语音识别的结果
            if event == 'result-generated':
                output = data['payload']['output']
                # sentence_end 表示该结果是中间结果还是最终结果
                # 当 sentence_end == false 时，为中间结果，不保证识别和翻译进度同步
                # 需要等待一句话结束（sentence_end == true）时同步
                if output.get('transcription', None) and output['transcription']['sentence_end']:
                    text.append(output['transcription']['text'])
            elif event == 'task-finished':
                break
            elif event == 'task-failed':
                raise Exception('ASR task failed')
        return ''.join(text)
