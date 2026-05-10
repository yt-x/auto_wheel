import unittest

from auto_wheel.state_model import ArtifactState, DependencyState, JobState, ResolutionStateSnapshot


class StateModelTests(unittest.TestCase):
    def test_job_state_values(self):
        self.assertEqual(JobState.RESOLVING_UV.value, "resolving_uv")
        self.assertEqual(JobState.COMPLETED_WITH_RISKS.value, "completed_with_risks")

    def test_dependency_state_values(self):
        self.assertEqual(DependencyState.WHEEL_READY.value, "wheel_ready")
        self.assertEqual(DependencyState.UNRESOLVED.value, "unresolved")

    def test_artifact_state_values(self):
        self.assertEqual(ArtifactState.GENERATED.value, "generated")
        self.assertEqual(ArtifactState.INVALID.value, "invalid")

    def test_resolution_snapshot_to_dict(self):
        snapshot = ResolutionStateSnapshot(
            job_state=JobState.RESOLVING_UV,
            stage="uv_compile",
            resolver="uv",
            reason="testing",
        )
        payload = snapshot.to_dict()
        self.assertEqual(payload["job_state"], "resolving_uv")
        self.assertEqual(payload["stage"], "uv_compile")
        self.assertEqual(payload["resolver"], "uv")
        self.assertIn("timestamp", payload)


if __name__ == "__main__":
    unittest.main()
