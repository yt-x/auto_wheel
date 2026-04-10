"""
Package inspector module - 自动检测包类型（二进制 wheel 或源码包）

此模块提供自动检测功能，在执行下载前查询 PyPI API，
判断每个包是否有可用的二进制 wheel，从而自动区分处理策略。
"""

import json
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import quote


class PackageInspector:
    """
    检查 PyPI 上的包信息，自动识别哪些包有可用 wheel，哪些只有源码
    
    示例:
        inspector = PackageInspector("3.9", "win_amd64")
        has_wheel, info = inspector.check_package("numpy", "1.24.0")
    """

    def __init__(
        self,
        python_version: str,
        platform: Optional[str] = None,
        implementation: str = "cp",
        abi: Optional[str] = None,
        timeout: int = 30,
        verbose: bool = False,
    ) -> None:
        """
        初始化检查器

        Args:
            python_version: 目标 Python 版本 (如: "3.9")
            platform: 目标平台 (如: "win_amd64", "manylinux2014_x86_64")
            implementation: Python 实现 (默认: "cp" for CPython)
            abi: Python ABI 标签
            timeout: API 请求超时时间（秒）
            verbose: 是否输出详细信息
        """
        self.python_version = python_version
        self.platform = platform
        self.implementation = implementation
        self.abi = abi or self._get_abi_tag()
        self.timeout = timeout
        self.verbose = verbose

        # 缓存已查询的包信息，避免重复请求
        self._cache: Dict[str, dict] = {}

    def _get_abi_tag(self) -> str:
        """根据 Python 版本生成 ABI 标签"""
        version_parts = self.python_version.split(".")
        major, minor = version_parts[0], version_parts[1]
        return f"{self.implementation}{major}{minor}"

    def _fetch_package_info(self, package_name: str) -> Optional[dict]:
        """
        从 PyPI API 获取包信息

        Args:
            package_name: 包名

        Returns:
            PyPI API 返回的 JSON 数据，失败返回 None
        """
        # 检查缓存
        if package_name in self._cache:
            return self._cache[package_name]

        # URL 编码包名（处理带有点或其他特殊字符的包名）
        encoded_name = quote(package_name)
        url = f"https://pypi.org/pypi/{encoded_name}/json"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "auto-wheel/1.0",
                }
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                self._cache[package_name] = data
                return data
        except urllib.error.HTTPError as e:
            if self.verbose:
                print(f"[WARN] 查询包 {package_name} 失败: HTTP {e.code}", file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            if self.verbose:
                print(f"[WARN] 查询包 {package_name} 失败: {e.reason}", file=sys.stderr)
            return None
        except Exception as e:
            if self.verbose:
                print(f"[WARN] 查询包 {package_name} 失败: {e}", file=sys.stderr)
            return None

    def check_package(
        self,
        package_name: str,
        package_version: Optional[str] = None
    ) -> Tuple[bool, dict]:
        """
        检查指定包是否有可用的二进制 wheel

        Args:
            package_name: 包名
            package_version: 指定版本（None 表示检查所有版本）

        Returns:
            (是否有 wheel, 详细信息字典)
            详细信息包括:
                - has_wheel: 是否有匹配的 wheel
                - has_sdist: 是否有源码包
                - wheels: 匹配的 wheel 列表
                - sdists: 匹配的源码包列表
                - error: 错误信息（如有）
        """
        info = {
            "has_wheel": False,
            "has_sdist": False,
            "wheels": [],
            "sdists": [],
            "error": None,
        }

        data = self._fetch_package_info(package_name)
        if data is None:
            info["error"] = f"无法获取包 {package_name} 的信息"
            return False, info

        urls = data.get("urls", [])

        # 筛选出 wheels 和 sdists
        wheels = [u for u in urls if u.get("packagetype") == "bdist_wheel"]
        sdists = [u for u in urls if u.get("packagetype") == "sdist"]

        info["has_sdist"] = len(sdists) > 0

        # 如果指定了版本，筛选匹配的版本
        if package_version:
            wheels = [w for w in wheels if w.get("filename", "").startswith(
                f"{package_name.replace('-', '_')}-{package_version}")
            ]
            sdists = [s for s in sdists if package_version in s.get("filename", "")]

        # 检查是否有匹配当前平台/Python 版本的 wheel
        matching_wheels = self._filter_compatible_wheels(wheels)

        info["wheels"] = matching_wheels
        info["sdists"] = sdists
        info["has_wheel"] = len(matching_wheels) > 0

        return info["has_wheel"], info

    def _filter_compatible_wheels(self, wheels: List[dict]) -> List[dict]:
        """
        筛选与当前平台/Python 版本兼容的 wheel

        Args:
            wheels: wheel 列表

        Returns:
            兼容的 wheel 列表
        """
        if not wheels:
            return []

        matching = []
        for wheel in wheels:
            filename = wheel.get("filename", "")
            
            # 检查是否匹配当前 Python 版本
            # wheel 文件名格式: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
            if not filename.endswith(".whl"):
                continue

            parts = filename[:-4].split("-")
            if len(parts) < 5:
                continue

            py_tag = parts[-3]  # 如: cp39, py3, py2.py3
            abi_tag = parts[-2]  # 如: cp39, abi3, none
            platform_tag = parts[-1]  # 如: win_amd64, manylinux2014_x86_64, any

            # 检查 Python 版本兼容性
            if not self._is_python_compatible(py_tag):
                continue

            # 检查平台兼容性
            if not self._is_platform_compatible(platform_tag):
                continue

            # 检查 ABI 兼容性
            if not self._is_abi_compatible(abi_tag):
                continue

            matching.append(wheel)

        return matching

    def _is_python_compatible(self, py_tag: str) -> bool:
        """检查 Python 标签是否兼容"""
        # 纯 Python 包标记为 py3, py2.py3, py2, py3-none-any
        if py_tag.startswith("py"):
            # 检查是否是 py3 或 py2.py3
            if "py3" in py_tag or py_tag == "py2.py3":
                return True
            return False

        # CPython 特定版本标记，如 cp39
        if py_tag.startswith("cp") or py_tag.startswith("pp"):
            expected_tag = f"{self.implementation}{self.python_version.replace('.', '')}"
            if py_tag == expected_tag:
                return True
            # 支持 abi3 兼容性的包（如 cryptography）
            # cp3x 格式的可以向下兼容
            if py_tag.startswith("cp3"):
                try:
                    wheel_minor = int(py_tag[3:])
                    target_minor = int(self.python_version.split(".")[1])
                    if wheel_minor <= target_minor:
                        return True
                except ValueError:
                    pass

        return False

    def _is_platform_compatible(self, platform_tag: str) -> bool:
        """检查平台标签是否兼容"""
        # 纯 Python 包
        if platform_tag == "any":
            return True

        # 如果没有指定目标平台，接受所有平台
        if not self.platform:
            return True

        target = self.platform.lower()
        tag = platform_tag.lower()

        # Windows
        if "win" in target:
            return "win" in tag

        # Linux (manylinux)
        if "linux" in target or "manylinux" in target:
            return "linux" in tag or "manylinux" in tag

        # macOS
        if "macos" in target or "darwin" in target:
            return "macos" in tag or "darwin" in tag

        return False

    def _is_abi_compatible(self, abi_tag: str) -> bool:
        """检查 ABI 标签是否兼容"""
        # 纯 Python 包或 abi3 兼容包
        if abi_tag == "none" or abi_tag == "abi3":
            return True

        # 检查是否匹配目标 ABI
        expected_abi = self.abi
        if abi_tag == expected_abi:
            return True

        # 对于 abi3，较新的 Python 版本可以使用较旧的 abi3 wheel
        if abi_tag.startswith("abi3"):
            return True

        return False

    def classify_packages(
        self,
        packages: List[str]
    ) -> Tuple[List[str], List[str], Dict[str, dict]]:
        """
        对包列表进行分类，自动识别哪些有 wheel，哪些只有源码

        Args:
            packages: 包名或要求规范列表（如 ["numpy==1.24.0", "requests>=2.0"]）

        Returns:
            (有 wheel 的包列表, 只有源码的包列表, 详细信息字典)
            详细信息字典的键是包名，值是 check_package 返回的 info
        """
        binary_packages = []
        source_packages = []
        details = {}

        print(f"\n[自动检测] 正在分析 {len(packages)} 个包的可用性...")
        print("-" * 50)

        for pkg_spec in packages:
            # 解析包名和版本
            pkg_name, pkg_version = self._parse_package_spec(pkg_spec)

            if self.verbose:
                print(f"  检查: {pkg_name}...", end=" ", flush=True)

            has_wheel, info = self.check_package(pkg_name, pkg_version)
            details[pkg_spec] = info

            if info["error"]:
                # 查询失败，假设有 wheel（让 pip 去尝试）
                if self.verbose:
                    print(f"[?] (查询失败，使用默认策略)")
                binary_packages.append(pkg_spec)
            elif has_wheel:
                binary_packages.append(pkg_spec)
                if self.verbose:
                    print(f"[OK] 找到 {len(info['wheels'])} 个兼容 wheel")
            else:
                source_packages.append(pkg_spec)
                if self.verbose:
                    print(f"[SRC] 只有源码包可用")

        print("-" * 50)
        print(f"检测结果: {len(binary_packages)} 个二进制包, {len(source_packages)} 个源码包")
        
        if source_packages and not self.verbose:
            print(f"源码包: {', '.join([self._parse_package_spec(p)[0] for p in source_packages])}")

        return binary_packages, source_packages, details

    def _parse_package_spec(self, spec: str) -> Tuple[str, Optional[str]]:
        """
        解析包规范，提取包名和版本

        Args:
            spec: 包规范，如 "numpy==1.24.0", "requests>=2.0", "flask"

        Returns:
            (包名, 版本或 None)
        """
        # 处理常见的版本指定符
        for sep in ["==", ">=", "<=", ">", "<", "!=", "~="]:
            if sep in spec:
                parts = spec.split(sep, 1)
                return parts[0].strip(), parts[1].strip()

        # 没有版本指定符
        return spec.strip(), None

    def get_package_metadata(self, package_name: str) -> Optional[dict]:
        """
        获取包的完整元数据

        Args:
            package_name: 包名

        Returns:
            包的元数据字典，失败返回 None
        """
        return self._fetch_package_info(package_name)
