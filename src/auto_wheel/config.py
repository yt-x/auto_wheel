"""
Configuration management module
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List


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

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration

        Args:
            config_path: Path to config file. If None, searches for config.json in current directory
        """
        self.config_data: Dict[str, Any] = self.DEFAULT_CONFIG.copy()

        # Try to load config file
        if config_path:
            self._load_config(config_path)
        else:
            # Search for config.json in current directory
            default_config = Path("config.json")
            if default_config.exists():
                self._load_config(str(default_config))

    def _load_config(self, config_path: str) -> None:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                self.config_data.update(user_config)
        except FileNotFoundError:
            print(f"Warning: Config file '{config_path}' not found. Using default configuration.")
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse config file '{config_path}': {e}")
            print("Using default configuration.")

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
