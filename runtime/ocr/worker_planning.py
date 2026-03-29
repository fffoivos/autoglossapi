#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from typing import Any


@dataclass
class WorkerPlanningInputs:
    gpu_memory_gib: float
    peak_worker_memory_gib: float
    headroom_gib: float = 15.0
    target_utilization: float = 0.80
    single_worker_utilization: float | None = None
    cpu_cores_per_gpu: float | None = None
    cpu_cores_per_worker: float | None = None
    files_per_gpu: int | None = None
    hard_max_workers: int | None = None


@dataclass
class WorkerPlanningRecommendation:
    memory_bound: int | None
    cpu_bound: int | None
    utilization_bound: int | None
    file_bound: int | None
    hard_cap_bound: int | None
    recommended_initial_workers: int
    candidate_sweep: list[int]
    limiting_factors: list[str]
    notes: list[str]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _positive_floor(value: float | None) -> int | None:
    if value is None or value <= 0:
        return None
    return max(1, math.floor(value))


def _positive_ceil(value: float | None) -> int | None:
    if value is None or value <= 0:
        return None
    return max(1, math.ceil(value))


def recommend_workers_per_gpu(inputs: WorkerPlanningInputs) -> WorkerPlanningRecommendation:
    usable_memory = max(inputs.gpu_memory_gib - inputs.headroom_gib, 0.0)
    memory_bound = _positive_floor(usable_memory / inputs.peak_worker_memory_gib)

    cpu_bound = None
    if inputs.cpu_cores_per_gpu and inputs.cpu_cores_per_worker and inputs.cpu_cores_per_worker > 0:
        cpu_bound = _positive_floor(inputs.cpu_cores_per_gpu / inputs.cpu_cores_per_worker)

    utilization_bound = None
    if inputs.single_worker_utilization and inputs.single_worker_utilization > 0:
        utilization_bound = _positive_ceil(inputs.target_utilization / inputs.single_worker_utilization)

    file_bound = None
    if inputs.files_per_gpu is not None:
        file_bound = max(1, int(inputs.files_per_gpu))

    hard_cap_bound = None
    if inputs.hard_max_workers is not None:
        hard_cap_bound = max(1, int(inputs.hard_max_workers))

    bounds = {
        "memory": memory_bound,
        "cpu": cpu_bound,
        "utilization": utilization_bound,
        "files": file_bound,
        "hard_cap": hard_cap_bound,
    }
    valid_bounds = {name: value for name, value in bounds.items() if value is not None}
    recommended = min(valid_bounds.values()) if valid_bounds else 1
    recommended = max(1, recommended)

    limiting_factors = [name for name, value in valid_bounds.items() if value == recommended]
    upper = max(valid_bounds.values()) if valid_bounds else recommended
    sweep_candidates = sorted(
        {
            candidate
            for candidate in (recommended - 1, recommended, recommended + 1)
            if candidate >= 1 and candidate <= upper
        }
    )

    notes = [
        "Use the result as an initial guess, not as a final answer.",
        "Exclude cold-start time when measuring single_worker_utilization.",
        "Measure peak_worker_memory_gib on hard pages, not only on easy PDFs.",
        "If the sweep shows similar throughput, prefer the smaller worker count for stability.",
    ]

    return WorkerPlanningRecommendation(
        memory_bound=memory_bound,
        cpu_bound=cpu_bound,
        utilization_bound=utilization_bound,
        file_bound=file_bound,
        hard_cap_bound=hard_cap_bound,
        recommended_initial_workers=recommended,
        candidate_sweep=sweep_candidates,
        limiting_factors=limiting_factors,
        notes=notes,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate a good starting workers-per-GPU value.")
    parser.add_argument("--gpu-memory-gib", type=float, required=True)
    parser.add_argument("--peak-worker-memory-gib", type=float, required=True)
    parser.add_argument("--headroom-gib", type=float, default=15.0)
    parser.add_argument("--target-utilization", type=float, default=0.80)
    parser.add_argument("--single-worker-utilization", type=float, default=None)
    parser.add_argument("--cpu-cores-per-gpu", type=float, default=None)
    parser.add_argument("--cpu-cores-per-worker", type=float, default=None)
    parser.add_argument("--files-per-gpu", type=int, default=None)
    parser.add_argument("--hard-max-workers", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    recommendation = recommend_workers_per_gpu(
        WorkerPlanningInputs(
            gpu_memory_gib=args.gpu_memory_gib,
            peak_worker_memory_gib=args.peak_worker_memory_gib,
            headroom_gib=args.headroom_gib,
            target_utilization=args.target_utilization,
            single_worker_utilization=args.single_worker_utilization,
            cpu_cores_per_gpu=args.cpu_cores_per_gpu,
            cpu_cores_per_worker=args.cpu_cores_per_worker,
            files_per_gpu=args.files_per_gpu,
            hard_max_workers=args.hard_max_workers,
        )
    )
    print(json.dumps(recommendation.to_json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
