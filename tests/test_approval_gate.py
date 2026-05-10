import unittest

from auto_wheel.approval_gate import should_block_download


class ApprovalGateTests(unittest.TestCase):
    def test_plan_only_never_blocks(self):
        self.assertFalse(should_block_download(True, False, True))

    def test_gate_blocks_when_not_approved(self):
        self.assertTrue(should_block_download(True, False, False))

    def test_gate_allows_when_approved(self):
        self.assertFalse(should_block_download(True, True, False))

    def test_without_gate_never_blocks(self):
        self.assertFalse(should_block_download(False, False, False))


if __name__ == "__main__":
    unittest.main()
