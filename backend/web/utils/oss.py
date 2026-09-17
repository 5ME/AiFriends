"""OSS 上传/签名/删除 —— 样本是用户语音，必须对象级私有 + 短期签名。

桶（OSS_BUCKET）实测是 public-read，所以**不能**依赖桶级设置：每个对象上传时显式 acl='private'。
"""
import datetime
import logging
import os
import uuid

import alibabacloud_oss_v2 as oss

logger = logging.getLogger(__name__)

OSS_TIMEOUT_SECONDS = 5
SAMPLE_PREFIX = 'samples/'

# "配置/凭据/权限"类服务端错误码 —— 归 500（给运维看），其余归 503（上游抖动）
OSS_CONFIG_ERROR_CODES = {
    'InvalidAccessKeyId', 'SignatureDoesNotMatch', 'NoSuchBucket',
    'AccessDenied', 'InvalidBucketName',
}

# SDK 侧"参数/命名"类异常 —— 同样是我们这边配置或代码写错了（如 OSS_BUCKET 写成非法桶名），
# 按 spec §7 归 500。用名字软取、不硬写类引用：某个名字在别的 SDK 版本里不存在时不会让 import 崩。
_CONFIG_ERROR_TYPE_NAMES = (
    'CredentialsBaseError', 'ParamInvalidError', 'ParamRequiredError',
    'ParamNullOrEmptyError', 'ParamNullError',
    'BucketNameInvalidError', 'ObjectNameInvalidError',
)
OSS_CONFIG_ERROR_TYPES = tuple(
    t for t in (getattr(oss.exceptions, n, None) for n in _CONFIG_ERROR_TYPE_NAMES)
    if isinstance(t, type))


class OssConfigError(Exception):
    """OSS 配置/凭据/权限错 —— 调用方应转 **500** 并打 ERROR 日志（spec §7）。"""


class OssUnavailableError(Exception):
    """OSS 上游不可用/超时 —— 调用方应转 **503**。"""


def _is_config_error(e: Exception) -> bool:
    """把 SDK 的异常体系收敛成"配置错 / 上游错"两类。

    ⚠️ 不能只判 `RuntimeError`：实测 SDK 的 **24 个异常类没有一个继承 `RuntimeError`**
    （`BaseError` / `ServiceError` / `CredentialsEmptyError` 都直接继承 `Exception`），
    所以"凭据错、bucket 不存在"这类**配置事故**会漏进兜底、被当成"上游抖动"返 503。

    ⚠️ 已知边界（Task 1 实测）：**桶名写错/桶不存在**时 SDK 抛的是 `OperationError`（`code=None`），
    与"网络不可达"**同一个异常类型、无法区分** → 这类会落到 503（可重试）而不是 500。
    白名单对"服务端带 code 的鉴权错"（如 `InvalidAccessKeyId`）仍然有效。
    不为了对齐文档去硬拆一个拆不开的东西 —— 用"打全量 ERROR 日志给运维"补足即可。
    """
    if isinstance(e, (RuntimeError, *OSS_CONFIG_ERROR_TYPES)):
        return True
    if isinstance(e, oss.exceptions.ServiceError):
        return (getattr(e, 'code', '') or '') in OSS_CONFIG_ERROR_CODES
    return False


def _wrap(fn):
    """跑一次 OSS 调用，把 SDK 异常归一成上面两个自有异常（SDK 分类知识只留在本模块）。

    ⚠️ **自家异常必须原样放行**：`_client()` 是在本函数的 lambda *内部* 调用的，而它自己也抛
    `OssConfigError` —— 不先放行就会被下面的兜底重新包成 `OssUnavailableError`，
    于是"缺环境变量"从 500 退化成 503（这条路径在收敛之前反而是对的，别把它改回去）。
    """
    try:
        return fn()
    except (OssConfigError, OssUnavailableError):
        raise
    except Exception as e:
        if _is_config_error(e):
            raise OssConfigError(str(e)) from e
        raise OssUnavailableError(str(e)) from e


def _client():
    missing = [k for k in ('OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_SECRET',
                           'OSS_BUCKET', 'OSS_REGION', 'OSS_ENDPOINT')
               if not os.getenv(k)]
    if missing:
        raise OssConfigError(f'OSS 配置缺失: {", ".join(missing)}')
    cfg = oss.config.load_default()
    cfg.credentials_provider = oss.credentials.StaticCredentialsProvider(
        access_key_id=os.environ['OSS_ACCESS_KEY_ID'],
        access_key_secret=os.environ['OSS_ACCESS_KEY_SECRET'])
    cfg.region = os.environ['OSS_REGION']
    cfg.endpoint = os.environ['OSS_ENDPOINT']
    cfg.connect_timeout = OSS_TIMEOUT_SECONDS
    cfg.readwrite_timeout = OSS_TIMEOUT_SECONDS
    return oss.Client(cfg)


def upload_private(data: bytes, suffix: str = 'mp3') -> str:
    """上传为**对象级 private**，返回对象 key。调用方负责用 presign_get 换签名 URL。"""
    key = f'{SAMPLE_PREFIX}{uuid.uuid4().hex}.{suffix}'
    _wrap(lambda: _client().put_object(oss.PutObjectRequest(
        bucket=os.environ['OSS_BUCKET'], key=key, body=data, acl='private')))
    return key


def presign_get(key: str, minutes: int = 5) -> str:
    req = oss.GetObjectRequest(bucket=os.environ['OSS_BUCKET'], key=key)
    return _wrap(lambda: _client().presign(
        req, expires=datetime.timedelta(minutes=minutes)).url)


def delete_object_quietly(key: str) -> None:
    """best-effort 删除：在 finally 里调用，绝不能把真正的错误盖掉。"""
    try:
        _client().delete_object(
            oss.DeleteObjectRequest(bucket=os.environ['OSS_BUCKET'], key=key))
    except Exception:
        logger.exception('OSS 对象删除失败（需人工清理）: key=%s', key)
