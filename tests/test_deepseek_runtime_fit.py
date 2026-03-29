from __future__ import annotations

import unittest

from runtime.ocr.deepseek_runtime_fit import DeepSeekRuntimeFacts, assess_deepseek_runtime_fit


class DeepSeekRuntimeFitTests(unittest.TestCase):
    def test_blackwell_with_old_cuda_and_missing_arch_fails(self) -> None:
        findings = assess_deepseek_runtime_fit(
            DeepSeekRuntimeFacts(
                gpu_model="NVIDIA RTX PRO 6000 Blackwell Server Edition",
                gpu_compute_capability="12.0",
                driver_version="580.105.08",
                torch_version="2.6.0+cu118",
                torch_cuda_version="11.8",
                torch_arch_list=["sm_80", "sm_86", "sm_90"],
                torch_cuda_available=True,
                allocation_ok=False,
                allocation_error="no kernel image is available for execution on the device",
                flash_attn_available=False,
                attention_fallback="eager",
                ocr_mode="grounded_markdown_heavy",
            )
        )
        by_id = {finding.check_id: finding for finding in findings}
        self.assertEqual(by_id["deepseek_fit:blackwell_cuda_runtime"].status, "fail")
        self.assertEqual(by_id["deepseek_fit:torch_arch_list"].status, "fail")
        self.assertEqual(by_id["deepseek_fit:cuda_allocation"].status, "fail")
        self.assertEqual(by_id["deepseek_fit:attention_backend"].status, "warn")
        self.assertEqual(by_id["deepseek_fit:ocr_mode"].status, "warn")

    def test_sdpa_fallback_on_supported_stack_passes_core_checks(self) -> None:
        findings = assess_deepseek_runtime_fit(
            DeepSeekRuntimeFacts(
                gpu_model="NVIDIA RTX PRO 6000 Blackwell Server Edition",
                gpu_compute_capability="12.0",
                driver_version="580.105.08",
                torch_version="2.9.1+cu130",
                torch_cuda_version="13.0",
                torch_arch_list=["sm_90", "sm_100", "sm_120"],
                torch_cuda_available=True,
                allocation_ok=True,
                flash_attn_available=False,
                attention_fallback="sdpa",
            )
        )
        by_id = {finding.check_id: finding for finding in findings}
        self.assertEqual(by_id["deepseek_fit:torch_arch_list"].status, "pass")
        self.assertEqual(by_id["deepseek_fit:attention_backend"].status, "pass")


if __name__ == "__main__":
    unittest.main()
