"""Compare embedding providers on the synthetic retrieval evaluation set.

Uses the production KnowledgeStore and provider interface unchanged. Network
access is blocked unless --allow-download is given, so runs are offline and
reproducible once a model is cached.

    cd backend
    python ../scripts/evaluate_embeddings.py --provider hashing
    HOME=/path/to/isolated/home python ../scripts/evaluate_embeddings.py \
        --provider onnx-minilm
"""

import argparse
import json
import re
import resource
import socket
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag.documents import KnowledgeDocument  # noqa: E402
from app.rag.embeddings import get_embeddings  # noqa: E402
from app.rag.store import KnowledgeStore  # noqa: E402

EVAL_PATH = REPO_ROOT / "data" / "synthetic" / "embedding_eval.json"
STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "by", "do", "does", "each", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "their", "there", "to", "we",
    "what", "when", "where", "who", "with",
}  # fmt: skip


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS


def block_network() -> None:
    def blocked(self, address):
        raise RuntimeError(f"Network access attempted: {address}")

    socket.socket.connect = blocked


def evaluate(provider: str) -> dict:
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    passages = {p["id"]: p["text"] for p in data["passages"]}
    documents = [
        KnowledgeDocument(
            source_id=pid,
            title=f"SYNTHETIC evaluation passage {pid}",
            publisher="RESQIVO synthetic test fixture (not an official source)",
            url=f"urn:resqivo:synthetic:{pid}",
            text=text,
            synthetic=True,
        )
        for pid, text in passages.items()
    ]

    started = time.perf_counter()
    store = KnowledgeStore(
        get_embeddings(provider), f"eval_{provider}".replace("-", "_")
    )
    store.ingest(documents)
    ingest_seconds = time.perf_counter() - started

    rows = []
    started = time.perf_counter()
    for query in data["queries"]:
        ranked = store.retrieve(query["text"], k=len(documents))
        order = [passage.source_id for passage in ranked]
        rank = order.index(query["relevant"]) + 1
        relevant = ranked[rank - 1].distance
        best_other = min(p.distance for p in ranked if p.source_id != query["relevant"])
        rows.append(
            {
                "id": query["id"],
                "type": query["type"],
                "rank": rank,
                "top_result": order[0],
                "relevant_distance": round(relevant, 4),
                "margin": round(best_other - relevant, 4),
                "shared_words": sorted(
                    words(query["text"]) & words(passages[query["relevant"]])
                ),
            }
        )
    query_seconds = time.perf_counter() - started

    def summary(selected: list[dict]) -> dict:
        n = len(selected)
        return {
            "queries": n,
            "top1": sum(r["rank"] == 1 for r in selected),
            "recall_at_3": sum(r["rank"] <= 3 for r in selected),
            "mrr": round(sum(1 / r["rank"] for r in selected) / n, 3),
            "mean_rank": round(sum(r["rank"] for r in selected) / n, 2),
        }

    return {
        "provider": provider,
        "corpus_passages": len(documents),
        "overall": summary(rows),
        "lexical": summary([r for r in rows if r["type"] == "lexical"]),
        "paraphrase": summary([r for r in rows if r["type"] == "paraphrase"]),
        "ingest_seconds": round(ingest_seconds, 3),
        "query_seconds_total": round(query_seconds, 3),
        # macOS reports bytes; Linux reports kilobytes.
        "peak_rss_mb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            / (1024 * 1024 if sys.platform == "darwin" else 1024),
            1,
        ),
        "queries_detail": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=["hashing", "onnx-minilm"])
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Permit network access, e.g. for the first ONNX model download.",
    )
    args = parser.parse_args()
    if not args.allow_download:
        block_network()
    print(json.dumps(evaluate(args.provider), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
