"""Offline, reproducible benchmark of RESQIVO's endpoints with fake models.

Measures three phases separately:
1. startup: time to import app.main in fresh interpreters (subprocesses);
2. warm-up: the first requests to each endpoint in this process;
3. steady state: a fixed number of requests at bounded concurrency.

The ASGI app runs in-process through httpx2's ASGITransport, so no socket is
opened. Network connections are blocked, ANTHROPIC_API_KEY is removed, tracing
is forced off, and /answer, /review and /draft-plan use the content-driven
fake model in app/evaluation/loadtest.py. Fake-model latency (0 ms by default)
says nothing about live Claude latency.

    cd backend
    python ../scripts/benchmark.py --output /tmp/resqivo-bench.json
    python ../scripts/benchmark.py --requests 400 --concurrency 16 --delay-ms 50
"""

import argparse
import asyncio
import json
import math
import os
import platform
import resource
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def make_offline() -> None:
    def blocked(self, address):
        raise RuntimeError(f"Network access attempted: {address}")

    socket.socket.connect = blocked
    os.environ.pop("ANTHROPIC_API_KEY", None)
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        os.environ[name] = "false"


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)], 3)


def summarize(latencies_ms: list[float], statuses: list[int], wall_s: float) -> dict:
    n = len(latencies_ms)
    ok = sum(200 <= s < 300 for s in statuses)
    result = {
        "requests": n,
        "succeeded": ok,
        "failed": n - ok,
        "timeouts": sum(s == 504 for s in statuses),
        "wall_seconds": round(wall_s, 3),
        "throughput_rps": round(n / wall_s, 1) if wall_s else None,
        "latency_ms": {
            "min": round(min(latencies_ms), 3),
            "median": round(statistics.median(latencies_ms), 3),
            "mean": round(statistics.fmean(latencies_ms), 3),
            "max": round(max(latencies_ms), 3),
        },
    }
    # Percentiles only where the sample supports them.
    if n >= 20:
        result["latency_ms"]["p95"] = percentile(latencies_ms, 95)
    if n >= 100:
        result["latency_ms"]["p99"] = percentile(latencies_ms, 99)
    return result


def measure_startup(runs: int) -> dict:
    code = (
        "import time; t = time.perf_counter(); import app.main; "
        "print(time.perf_counter() - t)"
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("ANTHROPIC_API_KEY", None)
    times = []
    for _ in range(runs):
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        times.append(float(out.stdout.strip()) * 1000)
    return {
        "runs": runs,
        "import_app_main_ms": {
            "first": round(times[0], 1),
            "median": round(statistics.median(times), 1),
            "max": round(max(times), 1),
        },
    }


def scenarios():
    from app.evaluation.loadtest import draft_body, plan_body

    return {
        "GET /health": ("GET", "/health", lambda i: {}),
        "POST /validate": (
            "POST",
            "/validate",
            lambda i: {"json": plan_body(990 + i % 20)},
        ),
        "POST /answer": (
            "POST",
            "/answer",
            lambda i: {"json": {"question": f"How is water stored for case-{i}?"}},
        ),
        "POST /review": (
            "POST",
            "/review",
            lambda i: {
                "json": {
                    "question": f"Review case-{i}",
                    "plan": plan_body(1001 + i % 5),
                }
            },
        ),
        "POST /draft-plan": (
            "POST",
            "/draft-plan",
            lambda i: {"json": draft_body(10 + i % 50)},
        ),
    }


async def run_requests(client, method, path, body_for, count, concurrency, offset):
    semaphore = asyncio.Semaphore(concurrency)
    latencies, statuses = [], []

    async def one(i):
        async with semaphore:
            started = time.perf_counter()
            response = await client.request(method, path, **body_for(offset + i))
            latencies.append((time.perf_counter() - started) * 1000)
            statuses.append(response.status_code)

    started = time.perf_counter()
    await asyncio.gather(*(one(i) for i in range(count)))
    return latencies, statuses, time.perf_counter() - started


async def benchmark(args) -> dict:
    import httpx2

    from app.evaluation.loadtest import install_offline_overrides
    from app.main import app
    from app.observability import METRICS

    install_offline_overrides(app, delay_seconds=args.delay_ms / 1000)
    results = {}
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(
        transport=transport, base_url="http://bench", timeout=120
    ) as client:
        for name, (method, path, body_for) in scenarios().items():
            first_started = time.perf_counter()
            first = await client.request(method, path, **body_for(0))
            first_ms = (time.perf_counter() - first_started) * 1000
            warm_lat, warm_status, warm_wall = await run_requests(
                client, method, path, body_for, args.warmup, 1, 1
            )
            lat, statuses, wall = await run_requests(
                client, method, path, body_for, args.requests, args.concurrency, 10_000
            )
            results[name] = {
                "first_request": {
                    "status": first.status_code,
                    "latency_ms": round(first_ms, 3),
                },
                "warm_up": summarize(warm_lat, warm_status, warm_wall)
                if args.warmup
                else None,
                "steady_state": summarize(lat, statuses, wall),
            }
    total = sum(
        c["value"]
        for c in METRICS.snapshot()["counters"]
        if c["name"] == "requests_total"
    )
    return {"endpoints": results, "requests_recorded_by_metrics": total}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--startup-runs", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if not (1 <= args.requests <= 5000 and 1 <= args.concurrency <= 64):
        parser.error("--requests must be 1-5000 and --concurrency 1-64.")
    if not (0 <= args.warmup <= 1000 and 0 <= args.delay_ms <= 5000):
        parser.error("--warmup must be 0-1000 and --delay-ms 0-5000.")

    make_offline()
    startup = measure_startup(args.startup_runs)
    rss_before = peak_rss_mb()
    measured = asyncio.run(benchmark(args))
    report = {
        "benchmark_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "offline, in-process ASGI, fake model",
        "live_model_calls": 0,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "parameters": {
            "requests_per_endpoint": args.requests,
            "concurrency": args.concurrency,
            "warmup_per_endpoint": args.warmup,
            "fake_model_delay_ms": args.delay_ms,
            "logging": "resqivo loggers not configured (events not emitted)",
        },
        "startup": startup,
        "peak_rss_mb": {"before_requests": rss_before, "after_requests": peak_rss_mb()},
        **measured,
        "notes": [
            "Fake-model latency is not a prediction of live Claude latency.",
            "Single process, in-process transport: excludes network, TLS and "
            "server worker overhead.",
            "Peak RSS is the process high-water mark (ru_maxrss), not per-request.",
        ],
    }
    text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    failed = sum(e["steady_state"]["failed"] for e in report["endpoints"].values())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
