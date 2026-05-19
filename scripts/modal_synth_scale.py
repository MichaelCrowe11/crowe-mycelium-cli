"""Parallel large-scale synthetic-data generation on Modal.

Fans out N concurrent shard-generation calls to Modal (each on its own GPU),
saves each completed shard to local shards/ as it returns, updates manifest,
and prints cost telemetry as it goes. Designed for 1K → 1M+ example runs.

Imports the same `generate_shard` function from modal_synth.py — no code dup.

Usage (with cost gate):
    modal run scripts/modal_synth_scale.py --total 1000 --shard-size 500 --parallel 4
    modal run scripts/modal_synth_scale.py --total 1000000 --shard-size 1000 --parallel 50 --gpu A10G
    modal run scripts/modal_synth_scale.py --total 100000 --gpu A100-40GB --parallel 20

A bare-bones cost projection prints first; you must pass --yes to actually run.
"""
import json, time
from datetime import datetime
from pathlib import Path

import modal

# Import the function from modal_synth so we share the image + logic.
# Modal will deploy the existing app's function; we just reuse the callable.
from modal_synth import app, generate_shard


# Rough cost guide ($/hr per Modal pricing)
GPU_HOURLY_USD = {
    "A10G":     1.10,
    "A100-40GB": 2.00,
    "A100-80GB": 3.40,
    "H100":     5.50,
    "H200":     6.50,
    "L4":       0.80,
    "L40S":     1.95,
}

# Empirical throughput on each GPU for Qwen-7B-4bit @ max_new_tokens=1024.
# Tune these from the 1K pilot (see EMPIRICAL_TUNE comment at bottom).
GPU_EXAMPLES_PER_HOUR = {
    "A10G":     650,
    "A100-40GB": 2200,
    "A100-80GB": 2400,
    "H100":     4500,
    "H200":     5200,
    "L4":       450,
    "L40S":     1500,
}


def project_cost(total: int, gpu: str) -> dict:
    rate = GPU_EXAMPLES_PER_HOUR.get(gpu, 600)
    hourly = GPU_HOURLY_USD.get(gpu, 1.50)
    hours = total / rate
    return {
        "gpu": gpu,
        "total_examples": total,
        "examples_per_gpu_hour": rate,
        "gpu_hours": round(hours, 2),
        "usd_estimate": round(hours * hourly, 2),
        "usd_per_1k": round(hourly * 1000 / rate, 3),
    }


@app.local_entrypoint()
def run(
    total: int = 1000,
    shard_size: int = 1000,
    parallel: int = 4,
    model: str = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    gpu: str = "A10G",
    batch_size: int = 8,
    max_new_tokens: int = 1024,
    seed_start: int = 100,
    yes: bool = False,
):
    n_shards = (total + shard_size - 1) // shard_size
    est = project_cost(total, gpu)

    print("=" * 60)
    print(f" Scale synth plan")
    print(f"   total examples : {total:,}")
    print(f"   shard size     : {shard_size}")
    print(f"   # shards       : {n_shards}")
    print(f"   parallelism    : {parallel}")
    print(f"   GPU            : {gpu}  (${GPU_HOURLY_USD.get(gpu, '?')}/hr)")
    print(f"   teacher model  : {model}")
    print(f"   batch / max_new: {batch_size} / {max_new_tokens}")
    print(f"   est GPU-hours  : {est['gpu_hours']}")
    print(f"   est cost USD   : ${est['usd_estimate']}  (${est['usd_per_1k']}/1K)")
    print("=" * 60)

    if not yes:
        print("\nDRY RUN. Pass --yes to actually launch.")
        return

    repo_root = Path("/root").exists() and Path("/root") or Path(__file__).resolve().parent.parent
    # local_entrypoint runs locally so __file__ resolves to the local path
    local_repo = Path(__file__).resolve().parent.parent
    shards_dir = local_repo / "shards"
    shards_dir.mkdir(exist_ok=True)

    # Determine starting shard index from what already exists
    existing = list(shards_dir.glob("magpie_*.jsonl")) + list(shards_dir.glob("scale_*.jsonl"))
    next_idx = 0
    for p in shards_dir.glob("scale_*.jsonl"):
        try:
            next_idx = max(next_idx, int(p.stem.split("_")[1]) + 1)
        except Exception:
            pass

    started_at = time.time()
    examples_done = 0
    cost_so_far = 0.0
    rate = GPU_EXAMPLES_PER_HOUR.get(gpu, 600)
    hourly = GPU_HOURLY_USD.get(gpu, 1.50)

    # Build (model, n_per_shard, batch, max_new, seed) tuples
    inputs = []
    for i in range(n_shards):
        n = min(shard_size, total - i * shard_size)
        if n <= 0:
            break
        inputs.append((model, n, batch_size, max_new_tokens, seed_start + i))

    # Stream results in completion order. .starmap returns an iterator that
    # yields results as the parallel calls finish.
    iter_results = generate_shard.starmap(inputs, order_outputs=False)

    for k, examples in enumerate(iter_results):
        shard_path = shards_dir / f"scale_{next_idx + k:05d}.jsonl"
        with open(shard_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        update_manifest(shards_dir, shard_path.name, len(examples), model)
        examples_done += len(examples)

        elapsed = time.time() - started_at
        eph = examples_done / max(elapsed, 1) * 3600  # examples per hour (wall, across all GPUs)
        gpu_hours_so_far = examples_done / rate
        cost_so_far = gpu_hours_so_far * hourly
        eta_remaining_hr = (total - examples_done) / max(eph, 1)

        print(f"[scale] {shard_path.name}  +{len(examples):>4d} ex  | "
              f"total {examples_done:>6,}/{total:,}  | "
              f"throughput {eph:,.0f} ex/hr  | "
              f"cost so far ~${cost_so_far:.2f}  | "
              f"ETA {eta_remaining_hr:.1f}h")

    final_cost = cost_so_far
    print(f"\n[scale] done.")
    print(f"  shards written  : {n_shards}")
    print(f"  examples done   : {examples_done:,}")
    print(f"  wall time       : {(time.time()-started_at)/60:.1f} min")
    print(f"  approx GPU cost : ${final_cost:.2f}")
    print(f"\nNext: commit + push shards via scripts/shard_and_push.ps1, then "
          f"modal run scripts/modal_train.py --shards 'shards/*.jsonl'")


def update_manifest(shards_dir, shard_name, n_examples, teacher):
    mf = shards_dir / "manifest.json"
    data = {"shards": []}
    if mf.exists():
        try:
            data = json.loads(mf.read_text())
        except Exception:
            pass
    data.setdefault("shards", []).append({
        "file": shard_name,
        "examples": n_examples,
        "teacher": teacher,
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    data["total_examples"] = sum(s["examples"] for s in data["shards"])
    data["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    mf.write_text(json.dumps(data, indent=2))


# EMPIRICAL_TUNE: After the 1K pilot, replace the EXAMPLES_PER_HOUR numbers
# above with what you actually measured. The pilot's printed
# "throughput X ex/hr" is exactly the number to plug in for that GPU.
