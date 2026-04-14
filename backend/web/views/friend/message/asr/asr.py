import asyncio
import json
import os
import uuid

import websockets
from openai import api_key
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class ASRView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        audio = request.FILES.get('audio')
        if not audio:
            return Response({'message': '音频不存在'},
                            status=status.HTTP_400_BAD_REQUEST)
        pcm_data = audio.read()
        text = asyncio.run(self.run_asr_task(pcm_data))
        return Response({'message': 'success', 'text': text})

    async def run_asr_task(self, pcm_data):
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
            async for msg in ws:
                if json.loads(msg)['header']['event'] == 'task-started':
                    # 收到 task-started 事件后，再发送待识别的音频流
                    break
            _, text = await asyncio.gather(
                self.asr_sender(ws, task_id, pcm_data),
                self.asr_receiver(ws)
            )
            return text

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
            # 如果任务结束或失败则退出
            elif event in ['task-finished', 'task-failed']:
                break
        return ''.join(text)
