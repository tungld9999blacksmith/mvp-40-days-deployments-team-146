"""Audit golden evidence and metadata against the configured Qdrant collection."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parents[4]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src")]

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore  # noqa: E402


STOPWORDS = {
    "có", "không", "là", "và", "của", "cho", "được", "trong", "khi",
    "với", "một", "các", "thì", "tại", "theo", "này", "đó", "để",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\d)[.,](?=\d)", "", value)
    return re.sub(r"\s+", " ", value).strip()


def meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[\w]+\b", normalize(value))
        if len(token) >= 2 and token not in STOPWORDS
    }


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=EVAL_DIR / "golden_set.jsonl")
    parser.add_argument("--collection")
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "indexed_evidence_audit.json")
    args = parser.parse_args()

    store = QdrantVectorStore(collection_name=args.collection)
    chunks = store.get_all_chunks()
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        by_doc[str(chunk.get("doc_id", ""))].append(chunk)

    rows = []
    for item in load_jsonl(args.golden):
        relevant_ids = item.get("relevant_doc_ids", [])
        relevant_chunks = [chunk for doc_id in relevant_ids for chunk in by_doc.get(doc_id, [])]
        indexed_text = "\n".join(str(chunk.get("content", "")) for chunk in relevant_chunks)
        normalized_text = normalize(indexed_text)
        keyword_checks = {
            keyword: normalize(keyword) in normalized_text
            for keyword in item.get("expected_keywords", [])
        }
        candidate_docs_by_keyword = {
            keyword: sorted({
                str(chunk.get("doc_id", ""))
                for chunk in chunks
                if normalize(keyword) in normalize(str(chunk.get("content", "")))
            })[:10]
            for keyword, found in keyword_checks.items()
            if not found
        }
        answer_tokens = meaningful_tokens(item.get("expected_answer", ""))
        indexed_tokens = meaningful_tokens(indexed_text)
        token_coverage = (
            len(answer_tokens & indexed_tokens) / len(answer_tokens) if answer_tokens else 1.0
        )
        expected_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", item.get("expected_answer", "")))
        normalized_numbers = {normalize(number) for number in expected_numbers}
        indexed_numbers = {normalize(number) for number in re.findall(r"\d+(?:[.,]\d+)*", indexed_text)}
        numbers_supported = normalized_numbers <= indexed_numbers

        expected_model = item.get("model") or "ALL"
        expected_category = item.get("category", "general")
        model_compatible = expected_model == "ALL" or any(
            str(chunk.get("metadata", {}).get("model", "ALL")) in {expected_model, "ALL"}
            for chunk in relevant_chunks
        )
        category_compatible = any(
            str(chunk.get("metadata", {}).get("category", "")) == expected_category
            for chunk in relevant_chunks
        )
        answer_supported = (
            bool(relevant_chunks)
            and all(keyword_checks.values())
            and numbers_supported
            # Expected answers are concise paraphrases, not extractive spans.
            # Keywords and numeric claims must match exactly; the lower token
            # threshold only checks that the remaining wording is grounded.
            and token_coverage >= 0.35
        )
        rows.append({
            "id": item["id"],
            "category": expected_category,
            "model": expected_model,
            "relevant_doc_ids": relevant_ids,
            "indexed_chunks": len(relevant_chunks),
            "missing_doc_ids": [doc_id for doc_id in relevant_ids if doc_id not in by_doc],
            "keyword_checks": keyword_checks,
            "candidate_docs_by_missing_keyword": candidate_docs_by_keyword,
            "expected_answer_token_coverage": round(token_coverage, 4),
            "numbers_supported": numbers_supported,
            "answer_supported": answer_supported,
            "model_compatible": model_compatible,
            "category_compatible": category_compatible,
        })

    summary = {
        "collection": store.collection_name,
        "points": store.count(),
        "queries": len(rows),
        "documents_complete": sum(not row["missing_doc_ids"] for row in rows),
        "keywords_complete": sum(all(row["keyword_checks"].values()) for row in rows),
        "answers_supported": sum(row["answer_supported"] for row in rows),
        "model_compatible": sum(row["model_compatible"] for row in rows),
        "category_compatible": sum(row["category_compatible"] for row in rows),
    }
    args.output.write_text(
        json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in rows:
        if not (
            row["answer_supported"]
            and row["model_compatible"]
            and row["category_compatible"]
        ):
            missing_keywords = [key for key, found in row["keyword_checks"].items() if not found]
            print(
                f"{row['id']}: missing_docs={row['missing_doc_ids']} "
                f"missing_keywords={missing_keywords} answer={row['answer_supported']} "
                f"model={row['model_compatible']} category={row['category_compatible']}"
            )
    return 0 if all(
        row["answer_supported"] and row["model_compatible"] and row["category_compatible"]
        for row in rows
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
