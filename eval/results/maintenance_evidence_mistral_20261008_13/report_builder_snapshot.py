"""Immutable audit and reporting for the maintenance evidence development run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "eval/results/maintenance_evidence_mistral_20261008_13"
OLD = ROOT / "eval/results/generation_mistral_policy_final_100_20261008_10"
PREFLIGHT = ROOT / "eval/results/generation_mistral_maintenance_preflight_20261008_13"
FULL = ROOT / "eval/results/generation_mistral_maintenance_100_20261008_13"
sys.path.insert(0, str(ROOT / "backend"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, payload):
    with (MASTER / name).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def hashes(folders):
    return {str(p.relative_to(ROOT)): digest(p) for folder in folders if folder.exists() for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def verify(mapping):
    changed = [n for n, h in mapping.items() if not (ROOT / n).is_file() or digest(ROOT / n) != h]
    return {"files_verified": len(mapping), "unchanged": not changed, "changed": changed}


def source_hashes():
    values = hashes([ROOT / "backend/src/agents", ROOT / "backend/src/infrastructure/llm", ROOT / "backend/tests/evaluation_v2", ROOT / "eval/datasets"])
    for name in ["backend/src/config.py", "backend/tests/test_agents/test_maintenance_evidence_gate.py"]:
        if (ROOT / name).exists():
            values[name] = digest(ROOT / name)
    return values


def rows(folder, name="case_results.jsonl"):
    return {r["case_id"]: r for line in (folder / name).read_text(encoding="utf-8").splitlines() if (r := json.loads(line))}


def prepare():
    old = hashes([ROOT / "eval/results", ROOT / "eval/datasets"])
    old.update({n: h for n, h in hashes([ROOT / "backend/tests/test_agents", ROOT / "backend/tests/evaluation"]).items() if Path(n).suffix != ".py"})
    corpus = hashes([ROOT / "data/knowledge/raw", ROOT / "data/knowledge/processed"])
    MASTER.mkdir(exist_ok=False)
    write("manifest.json", {"status": "DEVELOPMENT_NOT_ACCEPTANCE", "scope": "M07/M18/M23: preserve suspicious literal coolant values; never infer missing maintenance period actions", "model": "mistralai/mistral-small-2603", "previous_same_model": str(OLD.relative_to(ROOT)), "baseline_evidence": "eval/results/rag_v2_full_100_mistral_routed_20261007_01", "source_before": source_hashes(), "env_sha256": digest(ROOT / ".env"), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()})
    write("protected_previous_artifacts.json", old)
    write("protected_local_corpus.json", corpus)
    with (MASTER / "before_generator.py").open("x", encoding="utf-8") as stream:
        stream.write((ROOT / "backend/src/agents/tools/RAG/query/generator.py").read_text(encoding="utf-8"))
    previous = rows(OLD)
    inputs = rows(OLD, "fixed_inputs.jsonl")
    write("observed_failures.json", {"review_type": "CODEX_DRAFT_NOT_INDEPENDENT", "independent_labels": 0, "cases": [{"case_id": i, "question": previous[i]["question"], "delivered_answer": previous[i]["answer"], "response_metadata": previous[i]["response"]["metadata"], "frozen_input": inputs[i]["input"], "issue": "Source row says12.000km; delivered response substitutes120.000km" if i != "M23" else "Missing period columns do not establish replacement at40.000km"} for i in ["M07", "M18", "M23"]]})
    print(f"Prepared: {MASTER}; protected {len(old)} artifacts and {len(corpus)} corpus files")


def freeze(final=False):
    before = json.loads((MASTER / "manifest.json").read_text(encoding="utf-8"))["source_before"]
    after = source_hashes()
    changed = sorted(n.replace("\\", "/") for n in before.keys() | after.keys() if before.get(n) != after.get(n))
    assert changed == sorted(["backend/src/agents/tools/RAG/query/generator.py", "backend/src/agents/tools/RAG/query/maintenance_gate.py", "backend/tests/test_agents/test_maintenance_evidence_gate.py"]), changed
    write("source_revision_02.json" if final else "source_revision.json", {"source_hashes": after, "changed_from_before": changed})
    for name in changed:
        with (MASTER / (("revision_02_" if final else "revision_") + Path(name).name)).open("x", encoding="utf-8") as stream:
            stream.write((ROOT / name).read_text(encoding="utf-8"))
    print(f"Frozen {len(after)} files")


def summary(folder):
    data = list(rows(folder).values())
    events = [e for r in data for e in r["provider_events"]]
    costs = [e.get("usage", {}).get("cost_usd") for e in events]
    return {"rows": len(data), "errors": sum(bool(r["error"]) for r in data), "provider_requests": len(events), "provider_raw_json_valid": sum(r["raw_json_schema_valid"] is True for r in data), "pre_provider_answers": sum(not r["provider_events"] for r in data), "fallback_answers": sum(r["response"]["fallback_required"] for r in data), "citation_membership_valid": sum(r["citation_id_membership_valid"] for r in data), "gate_reasons": dict(Counter(r["response"]["metadata"].get("reason") for r in data if r["response"]["metadata"].get("evidence_gate"))), "provider_models": sorted({m for r in data for m in r["provider_models"]}), "known_cost_usd": sum(c for c in costs if c is not None), "cost_receipts_missing": sum(c is None for c in costs)}


def review():
    from src.agents.tools.RAG.query.procedure_gate import evidence_blocks
    from src.agents.tools.RAG.query.schemas import CitationItem
    from tests.evaluation_v2.source_review import map_answer_to_context

    old, new = rows(OLD), rows(FULL)
    old_inputs, new_inputs = rows(OLD, "fixed_inputs.jsonl"), rows(FULL, "fixed_inputs.jsonl")
    assert len(new) == 100 and new.keys() == old.keys()
    same = {i: {k: new_inputs[i][k] == old_inputs[i][k] for k in ["evidence_sha256", "sha256", "request_messages_sha256"]} for i in new}
    assert all(all(v.values()) for v in same.values())
    write("same_input_comparison.json", {"cases": same, "identical_cases": 100, "same_model_runtime_change": True})
    pairs, panels = [], []
    for identifier, candidate in new.items():
        frozen = new_inputs[identifier]["input"]
        citations = [CitationItem.model_validate(c) for c in frozen["citations"]]
        sources = [{"index": i, "document_id": c.document_id, "chunk_id": c.chunk_id, "title": c.title, "section": c.section, "text": body} for i, c, body in evidence_blocks(frozen["context_text"], citations)]
        mapped_old, mapping_old = map_answer_to_context(old[identifier]["answer"], old[identifier]["response"], sources)
        mapped_new, mapping_new = map_answer_to_context(candidate["answer"], candidate["response"], sources)
        pairs.append({"case_id": identifier, "question": candidate["question"], "previous_answer": old[identifier]["answer"], "candidate_answer": candidate["answer"], "previous_source_mapping": mapping_old, "candidate_source_mapping": mapping_new, "sources": sources, "candidate_metadata": candidate["response"]["metadata"]})
        titles = {"correctness": "Đúng nội dung", "citation_support": "Nguồn hỗ trợ", "task_success": "Đáp ứng yêu cầu"}
        controls = ''.join(f'<label>{titles[field]}<select data-key="{identifier}" data-field="{field}"><option value="">Chưa đánh giá</option><option value="pass">Đạt</option><option value="fail">Không đạt</option><option value="unsure">Chưa chắc</option></select></label>' for field in titles)
        esc = html.escape
        panels.append(f'<article id="{identifier}"><h2>{identifier}</h2><p>{esc(candidate["question"])}</p><details><summary>Đáp án trước sửa</summary><pre>{esc(old[identifier]["answer"])}</pre><p>{esc(str(mapping_old))}</p></details><h3>Đáp án cần review</h3><pre>{esc(candidate["answer"])}</pre><p>Ánh xạ citation tới nguồn gốc: {esc(str(mapping_new))}</p><details><summary>Đáp án theo số nguồn gốc và bằng chứng đầy đủ</summary><pre>{esc(mapped_old)}</pre><pre>{esc(mapped_new)}</pre><pre>{esc(json.dumps(sources,ensure_ascii=False,indent=2))}</pre></details>{controls}<label>Ghi chú<textarea data-key="{identifier}" data-field="notes"></textarea></label></article>')
    write("rag_before_after.json", {"independent_labels": 0, "cases": pairs})
    with (MASTER / "rag_independent_review.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "correctness", "citation_support", "task_success", "reviewer", "notes"])
        writer.writerows([i, "", "", "", "", ""] for i in new)
    # Reuse the reviewed export logic, scoped to the NEW producer hash.
    previous_js = (ROOT / "eval/results/rag_policy_mistral_20261008_09/rag_review.js").read_text(encoding="utf-8")
    old_sha = digest(OLD / "case_results.jsonl")
    assert old_sha in previous_js
    js = previous_js.replace(old_sha, digest(FULL / "case_results.jsonl")).replace("rag-policy-review-", "rag-maintenance-review-").replace("rag-source-gate-review.json", "rag-maintenance-review.json")
    with (MASTER / "rag_review.js").open("x", encoding="utf-8") as stream:
        stream.write(js)
    document = '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Maintenance RAG review</title><style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:20px}article{border:1px solid #aaa;margin:20px 0;padding:20px;scroll-margin-top:230px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:12px}label{display:inline-grid;margin:8px}textarea{width:400px}header{position:sticky;top:0;background:white;padding:10px}</style><header><h1>Review 100 câu RAG — cùng bằng chứng</h1><p>Development, chưa nghiệm thu. Điền tên reviewer, đọc nguồn theo ID chunk, chọn ba nhãn và ghi lý do. Chọn Chưa chắc khi chưa đủ căn cứ.</p><p>Ba ca vừa sửa: <a href="#M07">M07</a> · <a href="#M18">M18</a> · <a href="#M23">M23</a>. Tìm ca khác bằng Ctrl+F.</p><label>Reviewer<input id="reviewer"></label><button id="export">Export JSON</button><span id="count"></span></header>' + '\n'.join(panels) + '<script src="rag_review.js"></script></html>'
    with (MASTER / "rag_review.html").open("x", encoding="utf-8") as stream:
        stream.write(document)
    print("Built 100-case source-mapped review with blank independent labels")


def close():
    protected = verify(json.loads((MASTER / "protected_previous_artifacts.json").read_text(encoding="utf-8")))
    corpus = verify(json.loads((MASTER / "protected_local_corpus.json").read_text(encoding="utf-8")))
    latest_revision = MASTER / "source_revision_02.json"
    if not latest_revision.exists():
        latest_revision = MASTER / "source_revision.json"
    source = verify(json.loads(latest_revision.read_text(encoding="utf-8"))["source_hashes"])
    env = digest(ROOT / ".env") == json.loads((MASTER / "manifest.json").read_text(encoding="utf-8"))["env_sha256"]
    closed = {p.name: verify(json.loads(p.read_text(encoding="utf-8"))) for p in MASTER.glob("closed_*_hashes.json")}
    assert all(v["unchanged"] for v in [protected, corpus, source, *closed.values()]) and env
    write("preservation.json", {"previous_artifacts": protected, "corpus": corpus, "source": source, "closed_runs": closed, "env_unchanged": env})
    result = {"status": "DEVELOPMENT_NOT_ACCEPTANCE", "model": "mistralai/mistral-small-2603", "previous_same_model": summary(OLD), "preflight": summary(PREFLIGHT), "final_100": summary(FULL), "independent_labels": 0, "source_owner_adjudication": "PENDING", "reviewer_assignment": "USER_SELF_REVIEW_PENDING_LABELS", "offline": json.loads((MASTER / "offline_verification.json").read_text(encoding="utf-8")), "ruff": json.loads((MASTER / "ruff_final.json").read_text(encoding="utf-8")), "targeted_checks": json.loads((MASTER / "targeted_checks.json").read_text(encoding="utf-8"))}
    assert result["final_100"]["rows"] == 100 and result["final_100"]["errors"] == 0
    assert result["targeted_checks"]["passed"] == result["targeted_checks"]["total"] == 6
    write("result.json", result)
    write("completed_run_hashes.json", hashes([PREFLIGHT, FULL]))
    lines = ["# Bước 3 — bảng bảo dưỡng thiếu cột — 08/10/2026", "", "Đã hoàn tất đợt development này; chưa nghiệm thu production. Giữ Mistral Small 2603, Gemini embedding, golden/dataset/scorer và corpus. Không retrieval mới, gửi mail thật, ghi DB production hoặc restart app.", "", "M07: trích nguyên dòng coolant 12.000 km/120 tháng và yêu cầu xác minh; không tự sửa thành 120.000 km. M18: giữ tên hạng mục có trong bảng nhưng không gán thao tác/chu kỳ cho các dòng trống. M23: bảng thiếu cột không đủ căn cứ lập danh sách phụ tùng bắt buộc thay tại 40.000 km. Đây là xử lý thiếu bằng chứng, không chứng nhận lịch bảo dưỡng hiện hành.", "", "Probe phát hiện bảng đầy đủ viết gọn có ô trống cuối dòng bị hiểu nhầm là mất cột. Đã sửa parser giữ đúng các ô trống; [probe fail](compact_matrix_probe_01.json) và [probe cùng input sau sửa](compact_matrix_probe_02.json) được lưu riêng. Preflight/revision01/XML đầu giữ nguyên; revision02 được đóng trước full 100, không đổi code giữa run.", "", "| Run | Hoàn tất | Lỗi | Request JSON hợp lệ | Trả trước provider | Fallback |", "|---|---:|---:|---:|---:|---:|"]
    for label, key in [("Mistral trước", "previous_same_model"), ("Preflight", "preflight"), ("Mistral mới100", "final_100")]:
        s = result[key]
        lines.append(f"| {label} | {s['rows']} | {s['errors']} | {s['provider_raw_json_valid']}/{s['provider_requests']} | {s['pre_provider_answers']} | {s['fallback_answers']} |")
    lines.extend(["", f"Offline: {result['offline']}. [JUnit cuối](final_regression_01.xml); Ruff passed. [6/6 kiểm tra mục tiêu](targeted_checks.json) không thay thế semantic accuracy.", "", "[100 câu trước/sau](rag_review.html) và [hash cùng input](same_input_comparison.json). Citation membership chỉ kiểm identity, không thay citation support. Ba câu mục tiêu được xử lý trước provider, không tính thành model tự suy luận đúng. Không có retrieval mới.", "", "Đối chứng ở đây là run Mistral trước với cùng input/prompt/request schema. Paired comparison bên trong producer metrics dùng Gemma lịch sử với prompt-only JSON, nên khác điều kiện; số lỗi schema trong bản baseline sao chép không phải lỗi API hiện tại hoặc bằng chứng model A/B cùng điều kiện.", "", f"Chi phí receipt đợt này: {result['preflight']['known_cost_usd'] + result['final_100']['known_cost_usd']:.9f} USD; thiếu {result['preflight']['cost_receipts_missing'] + result['final_100']['cost_receipts_missing']} receipts.", "", f"[Preservation](preservation.json): {protected['files_verified']} artifact/dataset cũ và {corpus['files_verified']} file corpus không đổi; mọi run mới có thư mục riêng.", "", "Người dùng đã chọn trực tiếp review, nhưng chưa nộp nhãn; [hướng dẫn](REVIEW_INSTRUCTIONS.md) và [assignment](reviewer_assignment.json). Reviewer độc lập hiện vẫn 0 nhãn. Chủ nguồn còn phải xác minh coolant/scope/phiên bản; [queue nguồn](source_owner_review_queue.json) giữ trạng thái pending. Holdout, shortlist và HTTP/UI/TTFT/pilot chưa hoàn tất. Không sửa kỳ vọng golden hoặc rescore output cũ để nâng điểm."])
    with (MASTER / "report.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    write("closed_master_hashes.json", hashes([MASTER]))
    print(json.dumps({"final": result["final_100"], "protected": protected["files_verified"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "freeze", "freeze-final", "review", "close"])
    arg = parser.parse_args()
    {"prepare": prepare, "freeze": freeze, "freeze-final": lambda: freeze(final=True), "review": review, "close": close}[arg.phase]()
