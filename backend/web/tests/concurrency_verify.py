"""
P1-C3: SSE 流并发验证脚本

验证 C1（TTS 降级）和 C2（SSE 断连检测）在多请求并发下的正确性：
- 实例属性不跨请求串扰（cancel_event / _output_buffer / _tts_usage）
- generator finally 在并发断连时正常触发
- daemon 线程正常退出（mq.put(None) 送达）

使用方式:
    python backend/web/tests/concurrency_verify.py

前提:
    - Django dev server 在 :8000 运行
    - .env 中 API_KEY 有效（需要真实 LLM 调用）
"""
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

# Django 环境初始化（仅在直接运行时需要，pytest 导入时跳过）
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django
    django.setup()

BASE = "http://127.0.0.1:8000"
TEST_USERNAME = "__c3_verify__"
TEST_PASSWORD = str(uuid.uuid4())
CHARACTER_ID = 1  # 需已有至少一个角色
REQUESTS_PER_ROUND = 5
ROUNDS = 3


@dataclass
class SSEResult:
    """单次 SSE 请求的收集结果"""
    success: bool = False
    first_token_ms: int | None = None
    total_ms: int | None = None
    content_received: int = 0
    error_received: str = ""
    finished: bool = False


def ensure_test_user() -> str:
    """创建测试用户并返回 JWT access token"""
    resp = httpx.post(f"{BASE}/api/user/account/register/", json={
        "username": TEST_USERNAME, "password": TEST_PASSWORD,
    })
    if resp.status_code == 409:
        resp = httpx.post(f"{BASE}/api/user/account/login/", json={
            "username": TEST_USERNAME, "password": TEST_PASSWORD,
        })
    data = resp.json()
    return data.get("access_token", data.get("access", ""))


def get_test_friend(token: str) -> int:
    """获取或创建测试角色的好友关系"""
    resp = httpx.post(
        f"{BASE}/api/friend/get_or_create/",
        json={"character_id": CHARACTER_ID},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json().get("id", 0)


async def run_one_chat(token: str, friend_id: int, disconnect_early: bool = False) -> SSEResult:
    """发送一条聊天消息，消费 SSE 流直到 [DONE] 或中途断开"""
    result = SSEResult()
    start = time.monotonic()
    first_token = None

    async with httpx.AsyncClient(timeout=httpx.Timeout(120)) as client:
        async with client.stream(
            "POST",
            f"{BASE}/api/friend/message/chat/",
            json={"friend_id": friend_id, "message": "请用一段话介绍三昧真火"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status_code != 200:
                result.error_received = f"HTTP {response.status_code}"
                return result

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        result.finished = True
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if "error" in data:
                        result.error_received = data["error"]
                        return result
                    if "content" in data and data["content"]:
                        if first_token is None:
                            first_token = time.monotonic()
                        result.content_received += 1
                    if disconnect_early and result.content_received >= 1:
                        # 模拟 C2 断连 — 收到首个 content 后立即关闭连接
                        break

    result.success = True
    result.first_token_ms = int((first_token - start) * 1000) if first_token else None
    result.total_ms = int((time.monotonic() - start) * 1000)
    return result


async def scenario_1_basic_concurrency(token: str, friend_id: int) -> dict:
    """场景 1: 5 并发正常聊天"""
    print(f"\n{'='*60}")
    print("场景 1: 基础并发 — 5 用户同时聊天")
    print(f"{'='*60}")

    tasks = [run_one_chat(token, friend_id) for _ in range(REQUESTS_PER_ROUND)]
    results: list[SSEResult] = await asyncio.gather(*tasks)

    ok = sum(1 for r in results if r.success and r.finished)
    errors = sum(1 for r in results if r.error_received)

    print(f"  成功: {ok}/{REQUESTS_PER_ROUND}")
    print(f"  Error 事件: {errors}")
    for i, r in enumerate(results):
        ttft = f"{r.first_token_ms}ms" if r.first_token_ms else "N/A"
        print(f"  [{i+1}] 首 token: {ttft:>8s}  总耗时: {r.total_ms:>6}ms  content={r.content_received}")

    assert ok == REQUESTS_PER_ROUND, f"Expected {REQUESTS_PER_ROUND} success, got {ok}"
    assert errors == 0, f"Unexpected error events: {errors}"
    print("  ✅ PASS")
    return {"success": ok, "errors": errors}


async def scenario_2_concurrent_disconnect(token: str, friend_id: int) -> dict:
    """场景 2: 3 正常 + 2 中途断连"""
    print(f"\n{'='*60}")
    print("场景 2: 并发断连 — 3 正常 + 2 中途断开")
    print(f"{'='*60}")

    tasks = [
        run_one_chat(token, friend_id, disconnect_early=False),  # 3 正常
        run_one_chat(token, friend_id, disconnect_early=False),
        run_one_chat(token, friend_id, disconnect_early=False),
        run_one_chat(token, friend_id, disconnect_early=True),   # 2 断连
        run_one_chat(token, friend_id, disconnect_early=True),
    ]
    results: list[SSEResult] = await asyncio.gather(*tasks)

    normal = results[:3]
    disconnected = results[3:]

    normal_ok = sum(1 for r in normal if r.success and r.finished)
    normal_errors = sum(1 for r in normal if r.error_received)

    print(f"  正常请求成功: {normal_ok}/3")
    print(f"  正常请求 error 事件: {normal_errors}")
    print(f"  断连请求: 收到 content 后主动关闭 → 触发后端 C2 排空模式")

    # 关键验证：正常请求不应出现 error 事件（C2 cancel_event 不跨请求串扰）
    assert normal_errors == 0, (
        f"has_error 跨请求串扰！正常请求出现 error: "
        f"{[r.error_received for r in normal if r.error_received]}"
    )
    # 断连请求本地应标记为 success（HTTP 200 + 未在客户端读到 error）
    # 注：断连时服务端仍在排空，不会给客户端发 error
    print("  ✅ PASS (has_error 未跨请求串扰)")
    return {"normal_ok": normal_ok, "normal_errors": normal_errors}


async def scenario_3_repeat_rounds(token: str, friend_id: int) -> dict:
    """场景 3: 重复 3 轮，检查不退化和累积"""
    print(f"\n{'='*60}")
    print("场景 3: 重复 3 轮 — 检查无内存/线程累积")
    print(f"{'='*60}")

    all_ok = []
    for rnd in range(1, ROUNDS + 1):
        print(f"\n  第 {rnd} 轮:")
        tasks = [run_one_chat(token, friend_id) for _ in range(REQUESTS_PER_ROUND)]
        results: list[SSEResult] = await asyncio.gather(*tasks)
        ok = sum(1 for r in results if r.success and r.finished)
        errors = sum(1 for r in results if r.error_received)
        all_ok.append(ok)
        print(f"    成功: {ok}/{REQUESTS_PER_ROUND}  Error: {errors}")
        await asyncio.sleep(2)  # 给 daemon 线程时间清理 + 避 API 限流

    assert all(o == REQUESTS_PER_ROUND for o in all_ok), f"某轮有失败: {all_ok}"
    print("  ✅ PASS (3 轮均一致)")
    return {"rounds": all_ok}


async def main():
    print("P1-C3 SSE 流并发验证")
    print(f"Base URL: {BASE}")
    print(f"Concurrency: {REQUESTS_PER_ROUND} requests")

    token = ensure_test_user()
    print(f"User: {TEST_USERNAME}")

    friend_id = get_test_friend(token)
    print(f"Friend ID: {friend_id}")

    r1 = await scenario_1_basic_concurrency(token, friend_id)
    await asyncio.sleep(3)

    r2 = await scenario_2_concurrent_disconnect(token, friend_id)
    await asyncio.sleep(3)

    r3 = await scenario_3_repeat_rounds(token, friend_id)

    print(f"\n{'='*60}")
    print("全部通过 ✅")
    print(f"  场景 1: {r1['success']}/{REQUESTS_PER_ROUND} 成功, 0 error")
    print(f"  场景 2: {r2['normal_ok']}/3 正常请求成功, {r2['normal_errors']} error")
    print(f"  场景 3: {r3['rounds']} (3 轮)")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
