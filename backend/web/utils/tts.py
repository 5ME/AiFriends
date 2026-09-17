"""DashScope 语音合成的共用常量与"一次性合成"。

聊天主链路（chat.py）与音色试听共用同一组参数，保证"试听到的"等于"聊天听到的"。
音频以二进制帧返回（chat.py 靠 isinstance(msg, bytes) 判定），这里直接拼接。
"""
import asyncio
import json
import os
import uuid

import websockets

TTS_MODEL = 'cosyvoice-v3-flash'
TTS_FORMAT = 'mp3'
TTS_SAMPLE_RATE = 22050
TTS_VOLUME = 50
TTS_RATE = 1.0
TTS_PITCH = 1
TTS_TIMEOUT_SECONDS = 5


def _run_task_payload(task_id, voice_id):
    return {
        'header': {'action': 'run-task', 'task_id': task_id, 'streaming': 'duplex'},
        'payload': {
            'task_group': 'audio',
            'task': 'tts',
            'function': 'SpeechSynthesizer',
            'model': TTS_MODEL,
            'parameters': {
                'text_type': 'PlainText',
                'voice': voice_id,
                'format': TTS_FORMAT,
                'sample_rate': TTS_SAMPLE_RATE,
                'volume': TTS_VOLUME,
                'rate': TTS_RATE,
                'pitch': TTS_PITCH,
            },
            'input': {},
        },
    }


async def _synthesize_once_async(text, voice_id):
    wss_url = os.getenv('WSS_URL')
    api_key = os.getenv('API_KEY')
    task_id = uuid.uuid4().hex
    chunks = []
    async with websockets.connect(
            wss_url,
            additional_headers={'Authorization': f'Bearer {api_key}'},
            open_timeout=TTS_TIMEOUT_SECONDS) as ws:
        await ws.send(json.dumps(_run_task_payload(task_id, voice_id)))
        async for msg in ws:                      # 等 task-started
            if isinstance(msg, bytes):
                continue
            if json.loads(msg)['header']['event'] == 'task-started':
                break
        for action, payload in (('continue-task', {'input': {'text': text}}),
                                ('finish-task', {'input': {}})):
            await ws.send(json.dumps({
                'header': {'action': action, 'task_id': task_id, 'streaming': 'duplex'},
                'payload': payload,
            }))
        async for msg in ws:
            if isinstance(msg, bytes):
                chunks.append(msg)
                continue
            event = json.loads(msg)['header']['event']
            if event == 'task-failed':
                raise RuntimeError('TTS task-failed')
            if event == 'task-finished':
                break
    if not chunks:
        raise RuntimeError('TTS 未返回任何音频')
    return b''.join(chunks)


def synthesize_once(text, voice_id):
    """同步入口：跑一次完整合成，超时抛 TimeoutError。调用方负责转成 503。"""
    return asyncio.run(asyncio.wait_for(_synthesize_once_async(text, voice_id),
                                        timeout=TTS_TIMEOUT_SECONDS))
