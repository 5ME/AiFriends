import os

import requests


def create_voice(voice_url, prefix):
    headers = {
        "Authorization": f"Bearer {os.getenv('API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "create_voice",
            "target_model": "cosyvoice-v3-flash",
            "prefix": prefix,
            "url": voice_url,
        }
    }
    response = requests.post(url=os.getenv('VOICE_URL'), headers=headers, json=payload)
    return response.json()
