"""Run the offline RESQIVO evaluation and write a JSON report.

Always offline: network connections are blocked, model API keys are removed
from this process, LangSmith tracing is forced off, models are never
downloaded, and every index is in memory. No live model request is made.

    cd backend
    python ../scripts/run_evaluation.py --output /tmp/resqivo-eval.json
    python ../scripts/run_evaluation.py --providers hashing,onnx-minilm
    python ../scripts/run_evaluation.py --include-real-source   # WHO-01, local only

Exit codes: 0 when every evaluated case passed, 1 when any case failed, 2 for
an invalid dataset.
"""

import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(SCRIPTS_DIR))

PROVIDERS = ("hashing", "onnx-minilm")
EMBEDDING_EVAL_PATH = REPO_ROOT / "data" / "synthetic" / "embedding_eval.json"


def make_offline() -> None:
    """Block network access and make live model and tracing use impossible."""

    def blocked(self, address):
        raise RuntimeError(f"Network access attempted: {address}")

    socket.socket.connect = blocked
    for key in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        os.environ.pop(key, None)
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        os.environ[name] = "false"
    os.environ["RESQIVO_ALLOW_MODEL_DOWNLOAD"] = "false"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_retrieval(providers: list[str]):
    import evaluate_embeddings

    from app.evaluation.report import SkippedItem
    from app.evaluation.retrieval import synthetic_retrieval_track
    from app.rag.embeddings import EmbeddingModelUnavailableError

    runs, skipped = {}, []
    for provider in providers:
        try:
            runs[provider] = evaluate_embeddings.evaluate(provider)
        except EmbeddingModelUnavailableError:
            skipped.append(
                SkippedItem(
                    item=f"provider {provider}",
                    reason="Embedding model not in the local cache; downloads are "
                    "disabled.",
                )
            )
    data = json.loads(EMBEDDING_EVAL_PATH.read_text(encoding="utf-8"))
    dataset = {
        "path": "data/synthetic/embedding_eval.json",
        "version": data["version"],
        "sha256": _sha256(EMBEDDING_EVAL_PATH),
        "synthetic": True,
        "queries": len(data["queries"]),
        "passages": len(data["passages"]),
    }
    return synthetic_retrieval_track(runs, skipped, dataset), dataset


def real_source_retrieval(providers: list[str], include: bool):
    from app.evaluation.report import SkippedItem
    from app.evaluation.retrieval import real_source_retrieval_track
    from app.rag.config import DEFAULT_LOCAL_SOURCES_DIR
    from app.rag.embeddings import EmbeddingModelUnavailableError
    from app.rag.store import MAX_RESULTS

    if not include:
        reason = "Not requested; pass --include-real-source to evaluate WHO-01."
        return real_source_retrieval_track(
            {}, [SkippedItem(item="WHO-01", reason=reason)]
        )
    source = DEFAULT_LOCAL_SOURCES_DIR / "WHO-01.txt"
    questions = DEFAULT_LOCAL_SOURCES_DIR / "WHO-01.eval.json"
    missing = [p.name for p in (source, questions) if not p.is_file()]
    if missing:
        reason = f"Local, Git-ignored files missing: {', '.join(missing)}."
        return real_source_retrieval_track(
            {}, [SkippedItem(item="WHO-01", reason=reason)]
        )

    import evaluate_who_retrieval

    runs, skipped = {}, []
    for provider in providers:
        try:
            runs[provider] = evaluate_who_retrieval.evaluate(
                provider, source, questions, MAX_RESULTS
            )
        except EmbeddingModelUnavailableError:
            skipped.append(
                SkippedItem(item=f"provider {provider}", reason="Model not cached.")
            )
        except ValueError as exc:
            skipped.append(
                SkippedItem(item=f"provider {provider}", reason=f"Invalid set: {exc}")
            )
    return real_source_retrieval_track(runs, skipped)


def run(providers: list[str], include_real_source: bool):
    from app.evaluation.dataset import load_dataset
    from app.evaluation.runner import build_report, run_agentic_tracks

    loaded = load_dataset()
    synthetic, embedding_dataset = synthetic_retrieval(providers)
    real = real_source_retrieval(providers, include_real_source)
    return build_report(
        loaded,
        [synthetic, real, *run_agentic_tracks(loaded)],
        datasets={"retrieval_synthetic": embedding_dataset},
        providers=providers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--providers", default="hashing")
    parser.add_argument("--include-real-source", action="store_true")
    parser.add_argument("--output", help="Write the JSON report to this file.")
    args = parser.parse_args(argv)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = sorted(set(providers) - set(PROVIDERS))
    if unknown or not providers:
        parser.error(f"--providers must be from {', '.join(PROVIDERS)}")

    make_offline()
    try:
        report = run(providers, args.include_real_source)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    text = report.model_dump_json(indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    for name, summary in report.summary.items():
        print(
            f"{name}: {summary['status']}, {summary['passed']}/{summary['cases']} "
            f"passed, {summary['skipped']} skipped",
            file=sys.stderr,
        )
    return 1 if any(s["failed"] for s in report.summary.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
