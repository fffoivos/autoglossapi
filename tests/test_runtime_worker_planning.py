from __future__ import annotations

import unittest

from runtime.ocr.worker_planning import WorkerPlanningInputs, recommend_workers_per_gpu


class WorkerPlanningTests(unittest.TestCase):
    def test_g7e_style_inputs_produce_reasonable_guess(self) -> None:
        recommendation = recommend_workers_per_gpu(
            WorkerPlanningInputs(
                gpu_memory_gib=97.9,
                peak_worker_memory_gib=16.1,
                headroom_gib=15.0,
                single_worker_utilization=0.187,
                cpu_cores_per_gpu=24,
                cpu_cores_per_worker=6,
            )
        )
        self.assertEqual(recommendation.memory_bound, 5)
        self.assertEqual(recommendation.cpu_bound, 4)
        self.assertEqual(recommendation.utilization_bound, 5)
        self.assertEqual(recommendation.recommended_initial_workers, 4)
        self.assertEqual(recommendation.candidate_sweep, [3, 4, 5])
        self.assertIn("cpu", recommendation.limiting_factors)

    def test_missing_optional_inputs_still_returns_one_worker(self) -> None:
        recommendation = recommend_workers_per_gpu(
            WorkerPlanningInputs(
                gpu_memory_gib=24.0,
                peak_worker_memory_gib=20.0,
            )
        )
        self.assertEqual(recommendation.recommended_initial_workers, 1)
        self.assertEqual(recommendation.candidate_sweep, [1])


if __name__ == "__main__":
    unittest.main()
