import os

import requests


def delete_voice(voice_id: str):
    headers = {
        "Authorization": f"Bearer {os.getenv('API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "delete_voice",
            "voice_id": voice_id
        }
    }
    response = requests.post(url=os.getenv('VOICE_URL'), headers=headers, json=payload)
    return response.json()
