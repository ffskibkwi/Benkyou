"""配置加载与代理设置。

读取与解析 `config.ini`，并对 Gemini 通讯设置代理环境变量。
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class GeminiConfig:
    api_key: str
    model: str
    http_proxy: Optional[str]
    https_proxy: Optional[str]
    input_file: str


def _normalize_path(raw_path: str) -> str:
    path = raw_path.strip().strip('"').strip("'")
    path = os.path.expanduser(os.path.expandvars(path))
    return os.path.abspath(path)


def load_config(config_path: Optional[str] = None) -> GeminiConfig:
    """从 `config.ini` 加载配置。

    默认从当前文件所在目录查找 `config.ini`。
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"未找到配置文件：{config_path}")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")

    if not parser.has_section("gemini"):
        raise KeyError("配置缺少 [gemini] 段")
    if not parser.has_option("gemini", "api_key"):
        raise KeyError("[gemini] 段缺少 api_key 键")

    api_key = parser.get("gemini", "api_key").strip()
    model = parser.get("gemini", "model", fallback="gemini-1.5-flash").strip()

    http_proxy = None
    https_proxy = None
    if parser.has_section("proxy"):
        http_proxy = parser.get("proxy", "http", fallback="").strip() or None
        https_proxy = parser.get("proxy", "https", fallback="").strip() or None

    if not parser.has_section("file"):
        raise KeyError("配置缺少 [file] 段")
    if not parser.has_option("file", "input_file"):
        raise KeyError("[file] 段缺少 input_file 键")

    input_file = _normalize_path(parser.get("file", "input_file"))

    return GeminiConfig(
        api_key=api_key,
        model=model,
        http_proxy=http_proxy,
        https_proxy=https_proxy,
        input_file=input_file,
    )


def apply_proxy_environment(http_proxy: Optional[str], https_proxy: Optional[str]) -> None:
    """设置进程级代理环境变量，使下游 HTTP 客户端（如 requests）自动走代理。

    同时设置大小写两种形式（Windows 环境兼容）。
    传入 None 或空值将不会更改对应的变量。
    """
    def _set_if(value: Optional[str], key: str) -> None:
        if value:
            os.environ[key] = value

    _set_if(http_proxy, "http_proxy")
    _set_if(http_proxy, "HTTP_PROXY")
    _set_if(https_proxy, "https_proxy")
    _set_if(https_proxy, "HTTPS_PROXY")


