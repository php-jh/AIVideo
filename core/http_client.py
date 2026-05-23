"""
带重试的 HTTP 请求（缓解智谱等 HTTPS 偶发 SSLZeroReturnError / 连接被重置）。
"""
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from logger import get_logger

logger = get_logger("http_client")

# 网络层瞬时故障（含 TLS 握手被对端关闭）
TRANSIENT_REQUEST_ERRORS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_session: Optional[requests.Session] = None


def get_http_session(max_retries: int = 3) -> requests.Session:
    """复用 Session，但默认 Connection: close，减少长轮询时复用坏连接。"""
    global _session
    if _session is None:
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        sess = requests.Session()
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        sess.headers.setdefault("Connection", "close")
        _session = sess
    return _session


def request_with_retry(
    method: str,
    url: str,
    *,
    max_attempts: int = 5,
    backoff_sec: float = 2.0,
    session: Optional[requests.Session] = None,
    **kwargs,
) -> requests.Response:
    """
    对 SSLError / ConnectionError 等做指数退避重试。
    每次请求使用 Connection: close，避免 Windows 下空闲连接被服务端关闭后复用失败。
    """
    headers = dict(kwargs.pop("headers", None) or {})
    headers.setdefault("Connection", "close")
    kwargs["headers"] = headers

    sess = session or get_http_session()
    last_err: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return sess.request(method, url, **kwargs)
        except TRANSIENT_REQUEST_ERRORS as e:
            last_err = e
            if attempt >= max_attempts:
                break
            wait = min(backoff_sec * (2 ** (attempt - 1)), 30.0)
            logger.warning(
                "HTTP %s %s 失败 (%s)，%ss 后重试 (%s/%s)",
                method,
                url[:80],
                type(e).__name__,
                wait,
                attempt,
                max_attempts,
            )
            time.sleep(wait)
    assert last_err is not None
    raise last_err


def zhipu_ssl_hint() -> str:
    return (
        "（若为 SSL/TLS 连接中断：请检查网络、代理/VPN、防火墙；"
        "可稍后重试，或暂时改用「本地动效」/ SiliconFlow 图生视频。）"
    )


def is_transient_http_error(exc: BaseException) -> bool:
    """判断是否为可重试的瞬时网络/SSL 错误（含 RuntimeError 包装）。"""
    if isinstance(exc, TRANSIENT_REQUEST_ERRORS):
        return True
    if isinstance(exc, RuntimeError):
        s = str(exc).lower()
        return any(
            k in s
            for k in (
                "ssl",
                "tls",
                "connection",
                "eof",
                "max retries",
                "connectionpool",
                "远程主机",
            )
        )
    cause = getattr(exc, "__cause__", None)
    if cause and cause is not exc:
        return is_transient_http_error(cause)
    return False
