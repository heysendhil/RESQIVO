"""Evaluate retrieval on WHO-01 using locally prepared text and human-written questions.

Nothing is downloaded and nothing is persisted: the index is built in memory.
If the source text is missing, the script reports BLOCKED and exits with code 2.

    cd backend
    python ../scripts/evaluate_who_retrieval.py --provider hashing
    HOME=/path/to/isolated/home python ../scripts/evaluate_who_retrieval.py \
        --provider onnx-minilm

Inputs (both ignored by Git):
    knowledge/local/WHO-01.txt        plain text prepared from the official PDF
    knowledge/local/WHO-01.eval.json  questions with exact evidence spans
"""

import argparse
import datetime
import hashlib
import json
import socket
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.rag.chunking import DEFAULT_CHUNK_WORDS, DEFAULT_OVERLAP_WORDS  # noqa: E402
from app.rag.config import DEFAULT_LOCAL_SOURCES_DIR, DEFAULT_MANIFEST_PATH  # noqa: E402
from app.rag.embeddings import get_embeddings  # noqa: E402
from app.rag.ingest import load_approved_documents  # noqa: E402
from app.rag.manifest import load_manifest  # noqa: E402
from app.rag.store import MAX_RESULTS, KnowledgeStore  # noqa: E402

SOURCE_ID = "WHO-01"
# Spans up to the chunk overlap always fall entirely inside at least one chunk.
MAX_EVIDENCE_WORDS = DEFAULT_OVERLAP_WORDS


def normalise(text: str) -> str:
    return " ".join(text.split()).lower()


class EvalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^W\d{2,3}$")
    question: str = Field(min_length=1, max_length=1000)
    evidence: str = Field(min_length=1)
    page: str | None = None
    section: str | None = None

    @field_validator("evidence")
    @classmethod
    def evidence_length(cls, value: str) -> str:
        words = len(value.split())
        if not 3 <= words <= MAX_EVIDENCE_WORDS:
            raise ValueError(f"must be 3-{MAX_EVIDENCE_WORDS} words, got {words}")
        return value


class EvalSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    version: int = Field(ge=1)
    prepared_by: str = Field(min_length=1)
    prepared_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    questions: list[EvalQuestion] = Field(min_length=1)


def block_network() -> None:
    def blocked(self, address):
        raise RuntimeError(f"Network access attempted: {address}")

    socket.socket.connect = blocked


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_eval_set(path: Path, source_text: str, source_hash: str) -> EvalSet:
    eval_set = EvalSet.model_validate(json.loads(path.read_text(encoding="utf-8")))
    problems = []
    if eval_set.source_id != SOURCE_ID:
        problems.append(f"source_id must be {SOURCE_ID}")
    if eval_set.source_text_sha256 != source_hash:
        problems.append("source_text_sha256 does not match the local source text")
    ids = [q.id for q in eval_set.questions]
    if len(ids) != len(set(ids)):
        problems.append("question IDs must be unique")
    text = normalise(source_text)
    for question in eval_set.questions:
        if normalise(question.evidence) not in text:
            problems.append(
                f"{question.id}: evidence not found verbatim in source text"
            )
    if problems:
        raise ValueError("Invalid evaluation set:\n- " + "\n- ".join(problems))
    return eval_set


def evaluate(provider: str, source: Path, questions: Path, k: int) -> dict:
    source_text = source.read_text(encoding="utf-8")
    source_hash = sha256(source)
    eval_set = load_eval_set(questions, source_text, source_hash)

    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    documents = [
        d
        for d in load_approved_documents(manifest, source.parent)
        if d.source_id == SOURCE_ID
    ]
    store = KnowledgeStore(
        get_embeddings(provider), f"who_eval_{provider}".replace("-", "_")
    )
    chunks = store.ingest(documents)

    rows = []
    for question in eval_set.questions:
        evidence = normalise(question.evidence)
        ranked = store.retrieve(question.question, k=min(k, chunks))
        rank = next(
            (i + 1 for i, p in enumerate(ranked) if evidence in normalise(p.text)), None
        )
        rows.append(
            {
                "id": question.id,
                "rank": rank,
                "relevant_distance": round(ranked[rank - 1].distance, 4)
                if rank
                else None,
                "top_distance": round(ranked[0].distance, 4),
                "top_chunk_id": ranked[0].chunk_id,
                "page": question.page,
                "section": question.section,
            }
        )

    n = len(rows)
    return {
        "status": "COMPLETED",
        "synthetic": False,
        "source_id": SOURCE_ID,
        "provider": provider,
        "run_date": datetime.date.today().isoformat(),
        "source_text_sha256": source_hash,
        "questions_sha256": sha256(questions),
        "eval_set_version": eval_set.version,
        "chunk_words": DEFAULT_CHUNK_WORDS,
        "overlap_words": DEFAULT_OVERLAP_WORDS,
        "chunks": chunks,
        "k": min(k, chunks),
        "questions": n,
        "top1": sum(r["rank"] == 1 for r in rows),
        "top3": sum(r["rank"] is not None and r["rank"] <= 3 for r in rows),
        "not_found_in_top_k": sum(r["rank"] is None for r in rows),
        "mrr_at_k": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, choices=["hashing", "onnx-minilm"])
    parser.add_argument(
        "--source", default=str(DEFAULT_LOCAL_SOURCES_DIR / "WHO-01.txt")
    )
    parser.add_argument(
        "--questions", default=str(DEFAULT_LOCAL_SOURCES_DIR / "WHO-01.eval.json")
    )
    parser.add_argument("-k", type=int, default=MAX_RESULTS)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()

    source, questions = Path(args.source), Path(args.questions)
    missing = [str(p) for p in (source, questions) if not p.is_file()]
    if missing:
        print(json.dumps({"status": "BLOCKED", "missing_files": missing}, indent=2))
        return 2

    if not args.allow_download:
        block_network()
    try:
        result = evaluate(args.provider, source, questions, args.k)
    except (ValidationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
