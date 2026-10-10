"""Close the generation stage with separate provider and runtime gate counts."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import step4_generation as stage


def main():
    common = stage.common
    models = {}
    folders = []
    conditions = {}
    interventions = {}
    labels = 0
    frozen = common.read(stage.MASTER / "fixed_inputs.json")
    for key in stage.MODELS:
        models[key] = {}
        for phase in ("pilot", "full"):
            folder = stage.ROOT / "eval/results" / stage.run_name(phase, key)
            if not folder.exists():
                if phase == "pilot" or models[key]["pilot"]["pilot_eligible"]:
                    raise RuntimeError("Expected run missing")
                continue
            if not common.verify(common.read(folder / "closed_run_hashes.json"))["unchanged"]:
                raise RuntimeError("Closed producer changed")
            folders.append(folder)
            metrics = common.read(folder / "metrics.json")
            models[key][phase] = metrics
            if phase == "full" and not models[key]["pilot"]["pilot_eligible"]:
                raise RuntimeError("Full despite pilot failure")
            rows = [json.loads(line) for line in (folder / "case_results.jsonl").read_text(encoding="utf-8").splitlines()]
            expected_ids = stage.PILOT_IDS if phase == "pilot" else stage.IDS
            if [r["case_id"] for r in rows] != expected_ids[:len(rows)]:
                raise RuntimeError("IDs/order differ")
            interventions[f"{phase}_{key}"] = []
            for row in rows:
                if row["fixed_input_sha256"] != frozen[row["case_id"]]["fixed_input_sha256"]:
                    raise RuntimeError("Fixed input differs")
                for event in row["provider_events"]:
                    request = event["request"]
                    if request["messages"] != frozen[row["case_id"]]["messages"] or not request["extra_body"]["provider"]["require_parameters"]:
                        raise RuntimeError("Actual transport lost fixed messages/schema routing")
                    paired = {f: request[f] for f in ("messages", "response_format", "temperature", "max_tokens")}
                    conditions.setdefault(row["case_id"], set()).add(common.content_hash(paired))
                interventions[f"{phase}_{key}"].append({
                    "case_id": row["case_id"], "preprovider_gate": row["preprovider_gate"],
                    "response_metadata": row["response"]["metadata"],
                    "raw_contract_pass": row["raw_contract_pass"], "citation_structure": row["citation_structure"],
                    "runtime_fallback_required": row["response"]["fallback_required"], "error": row["error"],
                })
            with (folder / "human_review.csv").open(encoding="utf-8", newline="") as stream:
                labels += sum(any(r.get(f, "").strip() for f in ("correctness", "citation_support", "reviewer", "notes")) for r in csv.DictReader(stream))
    if labels or any(len(v) != 1 for v in conditions.values()):
        raise RuntimeError("Labels or actual paired conditions differ")
    preservation = stage.preservation()
    all_metrics = [v for phases in models.values() for v in phases.values()]
    total_cost = sum(v["known_cost_usd_partial"] for v in all_metrics)
    missing = sum(v["missing_cost_receipts"] for v in all_metrics)
    common.write(stage.MASTER / "comparison_conditions.json", {
        "actual_paired_request_hashes": {k: next(iter(v)) for k, v in conditions.items()},
        "same_original_queries_analysis_vehicle_evidence_prompt_schema_temperature_budget": True,
        "retrieval_calls": 0, "embedding_calls": 0,
        "differences": ["Mistral endpoint preference mistral/us,mistral/eu; Gemma automatic", "Sequential provider/cache/load effects; single development repeat"],
        "historical_pilot_prompt_changed": True, "historical_results_preserved": True,
        "semantic_accuracy": "NOT_MEASURED_REVIEW_DEFERRED",
    })
    common.write(stage.MASTER / "runtime_and_raw_audit.json", interventions)
    common.write(stage.MASTER / "result.json", {
        "scope": "FIXED_EVIDENCE_GENERATION_DEVELOPMENT", "models": models,
        "known_total_new_generation_spend_usd": total_cost, "missing_receipts": missing,
        "retrieval_calls": 0, "embedding_calls": 0, "independent_labels": 0,
        "semantic_accuracy": "NOT_MEASURED", "citation_claim_support": "NOT_MEASURED",
        "production_acceptance": False, "production_model_change": False,
        "gpt4o": "EXCLUDED_ALL_STAGES", "write": "INACTIVE", "report_controller_sha256": common.digest(Path(__file__)),
    })
    decision = {}
    for key, phases in models.items():
        full = phases.get("full")
        decision[key] = {"pilot_eligible": phases["pilot"]["pilot_eligible"],
                         "full_technical_eligible": bool(full and full["complete"] and full["technical_pass"] == full["selected"]),
                         "review": "DEFERRED_BY_USER", "production_change": False}
    common.write(stage.MASTER / "shortlist_by_stage.json", {
        "Generation": decision, "Rewrite": "Mistral retained per completed Rewrite screening",
        "Agent": "Existing Mistral/Gemma technical shortlist, no new Agent calls",
        "Write": "INACTIVE", "GPT4o": "EXCLUDED_ALL_STAGES", "application_model_change": False,
    })
    fields = ["phase", "model", "selected", "attempted", "technical_pass", "provider_calls", "strict_raw_contract_pass",
              "preprovider_cases", "errors", "provider_errors", "average_generation_seconds", "known_cost_usd_partial", "missing_cost_receipts"]
    lines = []
    with (stage.MASTER / "stage_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for key, phases in models.items():
            for phase, v in phases.items():
                writer.writerow({"phase": phase, "model": stage.MODELS[key], **{f: v[f] for f in fields if f in v}})
                mean = f"{v['average_generation_seconds']:.3f}" if v["average_generation_seconds"] is not None else "N/A"
                lines.append(f"| {phase} | {stage.MODELS[key]} | {v['attempted']}/{v['selected']} | {v['strict_raw_contract_pass']}/{v['provider_calls']} | {v['preprovider_cases']} | {v['errors']} | {mean} | {v['known_cost_usd_partial']:.9f} |")
    report = """# Bước 4 — generation Mistral/Gemma, 08/10/2026

Đã sửa duy nhất phần hướng dẫn định dạng JSON trong prompt generation; parser/schema/các gate nguồn giữ nguyên. Gemma M01 cũ đã có request JSON schema nhưng vẫn trả Markdown; giữ nguyên run/verdict cũ, không sửa điểm bằng parser hoặc làm sạch raw output. Revision mới chạy lại cả hai model cùng 6 câu pilot trước khi mở rộng 30 câu/model đủ điều kiện.

30 câu lấy nguyên văn từ golden lịch sử: cùng 24 câu golden ở Rewrite +6 câu golden khác; không thay golden bằng dataset mới, không phải holdout. Evidence 1–5 đoạn/câu lấy từ full RAG đã lưu và khóa hash, không retrieval/embedding mới. Các mốc/chính sách nguồn chưa review giữ nguyên.

| Lượt | Model | Hoàn tất | Raw JSON/provider calls | Runtime xử lý trước provider | Lỗi | Provider TB (giây) | Receipt generation (USD) |
| --- | --- | --- | --- | --- | --- | --- | ---: |
""" + "\n".join(lines) + f"""

Tổng receipt các attempt generation mới: **{total_cost:.9f} USD**, **{missing} receipt thiếu**. Provider latency chỉ đo các câu có model call, không gộp thời gian gate thành model latency, không phải TTFT hoặc latency toàn ứng dụng. Không cộng pilot/full cùng câu thành các case độc lập.

Đủ gate kỹ thuật của full không chứng nhận độ đúng nội dung. Citation membership/range/tag chỉ kiểm cấu trúc và danh tính; không chứng minh nguồn hỗ trợ claim. `runtime_and_raw_audit.json` ghi raw JSON, các gate, fallback/scope/conflict repair riêng. Correctness/claim support **chưa đánh giá**, người dùng đang tạm hoãn review, 0 nhãn độc lập.

Giữ Mistral làm baseline ứng dụng; xem số liệu full trước khi đề xuất stage khác. Chưa đổi `.env`, không gọi GPT-4o/Write/model thứ tư, không sửa golden/dataset/corpus hoặc kết quả cũ. Nếu full không đạt thì giữ lỗi và xử lý bằng revision/run mới; chỉ ứng viên đủ điều kiện kỹ thuật mới đi tới thu hẹp/cấu hình ghép. Bước 5 holdout ×3 và integration/UI chưa chạy.

Đã kiểm chứng cùng query/context/evidence/prompt/schema/config và request thực tế. Routing/cache/tải provider chưa được kiểm soát, các lượt là một lần development/model. Prompt cũ khác revision mới nên không dùng chênh lệch với run lịch sử để kết luận model A/B. Preservation/hash ở `final_preservation.json`, `closed_master_hashes.json`, từng producer; nguồn code trước sửa ở `before_generator.py`.
"""
    with (stage.MASTER / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(report)
    with (stage.MASTER / "report_controller.py").open("x", encoding="utf-8") as stream:
        stream.write(Path(__file__).read_text(encoding="utf-8"))
    common.write(stage.MASTER / "final_preservation.json", preservation)
    common.write(stage.MASTER / "completed_producer_hashes.json", common.hashes(folders))
    common.write(stage.MASTER / "closed_master_hashes.json", common.hashes([stage.MASTER]))
    verification = {"master": common.verify(common.read(stage.MASTER / "closed_master_hashes.json")),
                    "producers": common.verify(common.read(stage.MASTER / "completed_producer_hashes.json")), "preservation": preservation}
    common.write(stage.ROOT / "eval/results/step4_generation_verification_20261008_23.json", verification)
    print(json.dumps({"models": models, "spend_usd": total_cost, "preservation": preservation}, ensure_ascii=True))


if __name__ == "__main__":
    main()
