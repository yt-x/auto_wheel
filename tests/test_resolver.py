import subprocess
import unittest
from unittest.mock import patch

from auto_wheel.resolver import DependencyResolver


class DependencyResolverTests(unittest.TestCase):
    def test_convert_platform_fine_grained(self):
        self.assertEqual(
            DependencyResolver._convert_platform("manylinux2014_x86_64"),
            "x86_64-manylinux2014",
        )
        self.assertEqual(
            DependencyResolver._convert_platform("manylinux2014_aarch64"),
            "aarch64-manylinux2014",
        )
        self.assertEqual(
            DependencyResolver._convert_platform("win_amd64"),
            "x86_64-pc-windows-msvc",
        )
        self.assertEqual(
            DependencyResolver._convert_platform("macosx_11_0_arm64"),
            "aarch64-apple-darwin",
        )

    def test_resolve_without_uv_sets_state(self):
        resolver = DependencyResolver(
            python_version="3.9",
            platform="manylinux2014_x86_64",
            use_uv=False,
        )
        packages, used_uv, warning = resolver.resolve(["requests==2.31.0"])
        self.assertEqual(packages, ["requests==2.31.0"])
        self.assertFalse(used_uv)
        self.assertIsNone(warning)
        state = resolver.get_last_resolution_state()
        self.assertEqual(state["job_state"], "planning_ready")
        self.assertEqual(state["resolver"], "pip")
        self.assertEqual(state["normalized_platform"], "x86_64-manylinux2014")

    def test_unsatisfiable_uv_failure_is_classified(self):
        resolver = DependencyResolver(
            python_version="3.9",
            platform="manylinux2014_x86_64",
            use_uv=True,
        )
        failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=["uv", "pip", "compile"],
            stderr="No solution found when resolving dependencies",
            output="",
        )
        with patch("auto_wheel.resolver.shutil.which", return_value="uv"):
            with patch.object(resolver, "_resolve_with_uv", side_effect=failure):
                packages, used_uv, warning = resolver.resolve(["tensorflow==1.15.0"])

        self.assertEqual(packages, ["tensorflow==1.15.0"])
        self.assertFalse(used_uv)
        self.assertIn("不可满足", warning)
        state = resolver.get_last_resolution_state()
        self.assertEqual(state["job_state"], "resolving_pip_fallback")
        self.assertEqual(state["failure_kind"], "unsatisfiable")

    def test_tool_error_uv_failure_is_classified(self):
        resolver = DependencyResolver(
            python_version="3.9",
            use_uv=True,
        )
        failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=["uv", "pip", "compile"],
            stderr="internal uv error: io timeout",
            output="",
        )
        with patch("auto_wheel.resolver.shutil.which", return_value="uv"):
            with patch.object(resolver, "_resolve_with_uv", side_effect=failure):
                packages, used_uv, warning = resolver.resolve(["demo==1.0.0"])

        self.assertEqual(packages, ["demo==1.0.0"])
        self.assertFalse(used_uv)
        self.assertIn("已回退", warning)
        state = resolver.get_last_resolution_state()
        self.assertEqual(state["failure_kind"], "tool_error")

    def test_uv_unavailable_for_requirements_sets_fallback_state(self):
        resolver = DependencyResolver(
            python_version="3.9",
            use_uv=True,
        )
        with patch("auto_wheel.resolver.shutil.which", return_value=None):
            resolved, used_uv, warning = resolver.resolve_from_requirements_file("demo.txt")

        self.assertIsNone(resolved)
        self.assertFalse(used_uv)
        self.assertIn("未找到 uv", warning)
        state = resolver.get_last_resolution_state()
        self.assertEqual(state["job_state"], "resolving_pip_fallback")
        self.assertEqual(state["failure_kind"], "tool_error")


if __name__ == "__main__":
    unittest.main()
