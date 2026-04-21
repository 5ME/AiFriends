import os

import requests


def list_voice():
    headers = {
        "Authorization": f"Bearer {os.getenv('API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "voice-enrollment",
        "input": {
            "action": "list_voice",
            # "prefix": "announcer",
            "page_size": 1000,
            "page_index": 0
        }
    }
    response = requests.post(url=os.getenv('VOICE_URL'), headers=headers, json=payload)
    return response.json()
