"""
Configuration management module
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List


def default_user_config_path() -> Path:
    """
    Return the user-level config file path (cross-platform).

    - Windows: %APPDATA%/auto_wheel/config.json
    - POSIX:   $XDG_CONFIG_HOME/auto_wheel/config.json
               (defaults to ~/.config/auto_wheel/config.json)
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "auto_wheel" / "config.json"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "auto_wheel" / "config.json"
    return Path.home() / ".config" / "auto_wheel" / "config.json"


class Config:
    """Configuration manager for auto-wheel"""

    DEFAULT_CONFIG = {
        "index_url": "",  # Empty means use default PyPI
        "trusted_hosts": [],
        "extra_index_urls": [],
        "default_python_version": "3.9",
        "default_platform": "auto",
        "download_dir": "./downloads",
        "pip_timeout": 300,  # pip --timeout: 单个网络请求超时（秒）
        "retries": 3,
        "use_uv_resolver": True
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialize configuration.

        Lookup order (first hit wins, program defaults as final fallback):
            1. ``config_path`` explicitly given (CLI ``-c`` / GUI 配置文件字段）
            2. ``./config.json`` in the current working directory
            3. user-level config (see :func:`default_user_config_path`)
            4. ``DEFAULT_CONFIG``

        Values provided via CLI arguments or GUI fields always take
        precedence over any config file; this class only resolves files.

        Args:
            config_path: Path to config file. If None, searches the
                current directory, then the user-level config path.
        """
        self.config_data: Dict[str, Any] = self.DEFAULT_CONFIG.copy()
        # Path of the config file actually loaded; None when only defaults are used.
        self.loaded_from: Optional[str] = None

        if config_path:
            self._load_config(config_path)
        else:
            candidates = [Path("config.json"), default_user_config_path()]
            for candidate in candidates:
                if candidate.is_file():
                    self._load_config(str(candidate))
                    break

    def _load_config(self, config_path: str) -> None:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                self.config_data.update(user_config)
                self.loaded_from = config_path
        except FileNotFoundError:
            print(f"Warning: Config file '{config_path}' not found. Using default configuration.", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse config file '{config_path}': {e}", file=sys.stderr)
            print("Using default configuration.", file=sys.stderr)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config_data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self.config_data[key] = value

    @property
    def index_url(self) -> str:
        """Get index URL"""
        return self.config_data.get("index_url", "")

    @property
    def trusted_hosts(self) -> List[str]:
        """Get trusted hosts"""
        return self.config_data.get("trusted_hosts", [])

    @property
    def extra_index_urls(self) -> List[str]:
        """Get extra index URLs"""
        return self.config_data.get("extra_index_urls", [])

    @property
    def download_dir(self) -> str:
        """Get download directory"""
        return self.config_data.get("download_dir", "./downloads")

    @property
    def pip_timeout(self) -> int:
        """
        Get pip timeout value (单个网络请求超时，秒）

        用于传递给 pip 的 --timeout 参数
        """
        # 兼容旧配置中的 timeout 字段
        return self.config_data.get("pip_timeout", self.config_data.get("timeout", 300))

    @property
    def timeout(self) -> int:
        """
        获取超时配置（向后兼容）

        已废弃：请使用 pip_timeout 属性
        """
        return self.pip_timeout

    @property
    def retries(self) -> int:
        """Get retry count"""
        return self.config_data.get("retries", 3)

    @property
    def use_uv_resolver(self) -> bool:
        """Whether to enable uv-based dependency resolver"""
        return bool(self.config_data.get("use_uv_resolver", True))

    def get_pip_args(self) -> List[str]:
        """
        Generate pip command line arguments from configuration

        Returns:
            List of pip arguments
        """
        args = []

        # Add index URL if configured
        if self.index_url:
            args.extend(["--index-url", self.index_url])

        # Add extra index URLs
        for url in self.extra_index_urls:
            args.extend(["--extra-index-url", url])

        # Add trusted hosts
        for host in self.trusted_hosts:
            args.extend(["--trusted-host", host])

        # Add pip timeout (单个网络请求超时)
        args.extend(["--timeout", str(self.pip_timeout)])

        # Add retries
        args.extend(["--retries", str(self.retries)])

        return args
