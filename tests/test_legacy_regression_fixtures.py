import unittest

from auto_wheel.downloader import WheelDownloader
from auto_wheel.main import _summarize_stage_errors
from auto_wheel.resolver import DependencyResolver


class LegacyRegressionFixtureTests(unittest.TestCase):
    def test_thrift_no_wheel_reason_is_detected(self):
        errors = [
            {
                "stage": "wheel_only",
                "stderr": "ERROR: No matching distribution found for thrift==0.11.0",
                "stdout": "",
                "message": "",
            }
        ]
        reason = WheelDownloader._detect_no_wheel_reason(errors)
        self.assertIsNotNone(reason)
        self.assertIn("wheel", reason.lower())

    def test_mysqlclient_stage_summary_contains_source_failure_hint(self):
        errors = [
            {
                "stage": "wheel_only",
                "stderr": "ERROR: Could not find a version that satisfies the requirement mysqlclient==1.4.6",
            },
            {
                "stage": "source_fallback",
                "stderr": "ModuleNotFoundError: No module named 'distutils.msvccompiler'",
            },
        ]
        summary = _summarize_stage_errors(errors)
        self.assertIn("wheel_only", summary)
        self.assertIn("source_fallback", summary)
        self.assertIn("distutils", summary["source_fallback"])

    def test_tensorflow115_unsatisfiable_is_classified(self):
        resolver = DependencyResolver(python_version="3.9", use_uv=True)
        message = (
            "No solution found when resolving dependencies: "
            "tensorflow==1.15.0 has no wheels with a matching Python ABI tag cp39"
        )
        self.assertEqual(resolver._classify_uv_failure(message), "unsatisfiable")


if __name__ == "__main__":
    unittest.main()
