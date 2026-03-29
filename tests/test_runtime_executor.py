from __future__ import annotations

import unittest

from runtime.aws.task_execution import derive_execution_plan


class RuntimeExecutorPlanningTests(unittest.TestCase):
    def test_repair_task_uses_safe_execution_defaults(self) -> None:
        task = {
            "task_type": "repair_glossapi_host",
            "provider": "aws",
            "requirements": {
                "expect_gpu": True,
                "needs_rust": True,
                "needs_cleaner": True,
                "needs_deepseek_ocr": True,
            },
            "existing_host": {
                "repo_path": "/opt/dlami/nvme/glossapi/glossAPI",
                "runtime_python": "/opt/dlami/nvme/glossapi/glossAPI/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python",
            },
        }
        plan = derive_execution_plan(task)
        self.assertEqual(plan["bootstrap_mode"], "repair")
        self.assertFalse(plan["update_repo"])
        self.assertEqual(plan["default_ssh_user"], "ubuntu")
        self.assertIn("--needs-cleaner", plan["readiness_flags"])
        self.assertTrue(plan["run_ocr_smoke_test"])
        self.assertEqual(plan["runtime_python_candidates"][0], task["existing_host"]["runtime_python"])

    def test_provision_task_updates_repo_and_skips_ocr_smoke_when_not_needed(self) -> None:
        task = {
            "task_type": "provision_glossapi_host",
            "provider": "hetzner",
            "requirements": {
                "needs_rust": True,
                "needs_cleaner": True,
                "needs_deepseek_ocr": False,
            },
            "resolved_runtime_defaults": {
                "target_dir": "/srv/glossapi/glossAPI",
            },
        }
        plan = derive_execution_plan(task)
        self.assertEqual(plan["bootstrap_mode"], "provision")
        self.assertTrue(plan["update_repo"])
        self.assertEqual(plan["default_ssh_user"], "foivos")
        self.assertFalse(plan["run_ocr_smoke_test"])
        self.assertEqual(plan["target_dir"], "/srv/glossapi/glossAPI")


if __name__ == "__main__":
    unittest.main()
