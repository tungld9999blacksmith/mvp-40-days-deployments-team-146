"""Close the GPT-4o Agent extension with explicit original/recovery reporting."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter

from step4_gpt4o_followup import (
    BASELINES,
    MASTER,
    MODEL,
    ROOT,
    RUNS,
    frozen_source,
    raw_audit,
    read,
    write,
)
from step4_gpt4o_recovery import RECOVERY
from step4_smoke import digest, hashes, load_rows, percentile, verify


def row_metrics(rows):
    times = [r["trace"]["latency_seconds"] for r in rows]
    costs = [r["trace"].get("provider_cost_usd") for r in rows]
    return {
        "attempted": len(rows), "passed": sum(r["metrics"]["task_passed"] for r in rows),
        "errors": sum(bool(r["trace"].get("error")) for r in rows),
        "safety_violations": sum(len(r["metrics"]["safety_violations"]) for r in rows),
        "raw_argument_error_cases": sum(bool(r["metrics"]["raw_argument_errors"]) for r in rows),
        "truncated_cases": sum(bool(r["trace"]["truncated"]) for r in rows),
        "actual_models": sorted({m for r in rows for m in r["trace"]["provider_models"]}),
        "mean_seconds": statistics.fmean(times), "p90_seconds": percentile(times, .9),
        "known_cost_usd": sum(c for c in costs if isinstance(c, (int, float))),
        "missing_cost_cases": sum(c is None for c in costs),
        "input_tokens": sum(u.get("input_tokens", 0) for r in rows for u in r["trace"].get("usage", [])),
        "output_tokens": sum(u.get("output_tokens", 0) for r in rows for u in r["trace"].get("usage", [])),
        "categories": {c: {"attempted": n, "passed": sum(r["metrics"]["task_passed"] for r in rows if r["category"] == c)}
                       for c, n in Counter(r["category"] for r in rows).items()},
    }


def main():
    manifest = read(MASTER / "manifest.json")
    initial = read(MASTER / "result.json")
    recovery = read(MASTER / "recovery_summary.json")
    plan = read(MASTER / "recovery_plan.json")
    original = ROOT / "eval/results" / RUNS["full"]
    preflight = ROOT / "eval/results" / RUNS["preflight"]
    rows = []
    for ref in recovery["unique_case_coverage"]:
        producer = ROOT / ref["producer"]
        if digest(producer / "case_results.jsonl") != ref["producer_results_sha256"]:
            raise RuntimeError("Referenced producer changed")
        rows.append(next(r for r in load_rows(producer) if r["case_id"] == ref["case_id"]))
    if [r["case_id"] for r in rows] != manifest["selected_ids"]:
        raise RuntimeError("Unique case coverage differs")
    configurations = {name: read(folder / "manifest.json")["configuration"]
                      for name, folder in BASELINES.items()}
    configurations["gpt4o_original"] = read(original / "manifest.json")["configuration"]
    configurations["gpt4o_recovery"] = read(RECOVERY / "manifest.json")["configuration"]
    baseline = configurations["mistral"]
    common_fields = ("repeats", "max_tokens", "temperature", "timeout", "clock", "dataset_sha256",
                     "rag_mode", "business_services", "baseline_runtime", "scorer_version")
    comparisons = {name: {field: config[field] == baseline[field] for field in common_fields}
                   for name, config in configurations.items()}
    for name, folder in (BASELINES | {"gpt4o_original": original, "gpt4o_recovery": RECOVERY}).items():
        comparisons[name]["schema_identical"] = digest(folder / "schema_snapshot.json") == digest(BASELINES["mistral"] / "schema_snapshot.json")
        comparisons[name]["selected_ids_correct"] = configurations[name]["selected_ids"] == (plan["selected_ids"] if name == "gpt4o_recovery" else manifest["selected_ids"])
    if not all(all(c.values()) for c in comparisons.values()):
        raise RuntimeError("Frozen comparison conditions differ")
    covered = row_metrics(rows)
    if covered["actual_models"] != [MODEL]:
        raise RuntimeError("Unexpected actual provider model")
    all_new_rows = load_rows(preflight) + load_rows(original) + load_rows(RECOVERY)
    if any(r["metrics"]["semantic_correctness"] != "NOT_MEASURED" for r in all_new_rows):
        raise RuntimeError("Unexpected semantic labels")
    label_count = 0
    for folder in (preflight, original, RECOVERY):
        with (folder / "human_review.csv").open(encoding="utf-8", newline="") as stream:
            human_rows = list(csv.DictReader(stream))
        for row in human_rows:
            label_count += any(row.get(k, "").strip() for k in ("correctness", "citation_support", "task_success", "reviewer", "notes"))
    if label_count:
        raise RuntimeError("Unexpected independent review labels")
    budget = row_metrics(all_new_rows)
    write("completion_result.json", {
        "scope": "DEVELOPMENT_AGENT_SMOKE", "original_run": initial["models"]["gpt4o"],
        "original_not_attempted_ids": plan["not_attempted_ids"], "recovery_run": recovery["recovery"],
        "coverage_across_runs": covered, "single_full_repeat": False,
        "covered_row_references": recovery["unique_case_coverage"],
        "coverage_raw_audit": raw_audit(rows), "common_conditions": comparisons,
        "known_total_new_spend_usd": budget["known_cost_usd"],
        "missing_cost_cases_all_attempts": budget["missing_cost_cases"],
        "cost_is_lower_bound": bool(budget["missing_cost_cases"]),
        "independent_labels": 0, "review_deferred": True, "production_acceptance": False,
        "pacing_difference": "original 1 second, recovery 15 seconds between cases; sleeps excluded from per-case latency",
        "report_controller_sha256": digest(ROOT / "eval/step4_gpt4o_report.py"),
    })
    columns = ["stage", "model", "scope", "selected", "attempted", "passed", "errors", "safety_violations",
               "raw_argument_error_cases", "mean_seconds", "p90_seconds", "known_cost_usd", "missing_cost_cases", "semantic_review"]
    with (MASTER / "stage_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        entries = [("mistralai/mistral-small-2603", "single_run", 30, initial["models"]["mistral"]),
                   ("google/gemma-4-26b-a4b-it", "single_run", 30, initial["models"]["gemma"]),
                   (MODEL, "original_incomplete", 30, initial["models"]["gpt4o"]),
                   (MODEL, "targeted_recovery", 8, recovery["recovery"]),
                   (MODEL, "unique_coverage_across_runs_not_independent_repeat", 30, covered)]
        for model, scope, selected, values in entries:
            writer.writerow({"stage": "Agent", "model": model, "scope": scope, "selected": selected,
                             **{k: values[k] for k in columns if k in values}, "semantic_review": "DEFERRED"})
    write("shortlist_by_stage.json", {
        "Agent": {
            "mistralai/mistral-small-2603": "KEEP_BASELINE: 30/30 scorer, lower observed cost than GPT-4o; semantic review deferred",
            "google/gemma-4-26b-a4b-it": "DEVELOPMENT_COST_CANDIDATE: 30/30 scorer; slower; semantic review deferred",
            MODEL: "RESERVE: original 5 provider 429 errors; targeted recovery recorded separately; substantially higher observed cost, no proven semantic advantage",
        },
        "Rewrite": "NOT_RUN: next stage is offline subset/criteria lock, then 3-model pilot",
        "Generation": "Mistral/Gemma 6-case pilot retained; GPT-4o NOT_RUN; no independent semantic review",
        "Write": "INACTIVE: no GPT-4o reviewer calls", "production_model_change": False,
    })
    first = initial["models"]["gpt4o"]
    rec = recovery["recovery"]
    m = initial["models"]["mistral"]
    g = initial["models"]["gemma"]
    ratio = covered["known_cost_usd"] / m["known_cost_usd"]
    report = f"""# Bước 4 — bổ sung GPT-4o cho Agent, 08/10/2026

Đã chạy preflight, lượt Agent GPT-4o và chạy bù có pacing. Giữ Mistral Small 2603 trong ứng dụng. Đây là sàng lọc kỹ thuật development; review nội dung đang tạm hoãn, 0 nhãn độc lập, chưa nghiệm thu production.

## Kết quả thực tế

| Model / lượt | Selected | Attempted | PASS scorer | Lỗi provider | Latency TB / p90 (giây) | Receipt đã biết (USD) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| Mistral Small 2603, lượt cũ giữ nguyên | 30 | 30 | 30 | 0 | {m['mean_seconds']:.3f} / {m['p90_seconds']:.3f} | {m['known_cost_usd']:.9f} |
| Gemma 4 26B A4B, lượt cũ giữ nguyên | 30 | 30 | 30 | 0 | {g['mean_seconds']:.3f} / {g['p90_seconds']:.3f} | {g['known_cost_usd']:.9f} |
| GPT-4o, lượt đầu | 30 | {first['attempted']} | {first['passed']} | {first['errors']} | {first['mean_seconds']:.3f} / {first['p90_seconds']:.3f} | {first['known_cost_usd']:.9f}, thiếu {first['missing_cost_cases']} receipt |
| GPT-4o, chạy bù 8 case | 8 | {rec['attempted']} | {rec['passed']} | {rec['errors']} | {rec['mean_seconds']:.3f} / {rec['p90_seconds']:.3f} | {rec['known_cost_usd']:.9f} |
| GPT-4o, phủ 30 ID qua hai lượt | 30 | {covered['attempted']} | {covered['passed']} | {covered['errors']} trong các dòng được chọn | {covered['mean_seconds']:.3f} / {covered['p90_seconds']:.3f} | {covered['known_cost_usd']:.9f} |

Hàng cuối lấy 22 case PASS lượt đầu và kết quả chạy bù cho 8 ID còn lại. **Không phải một full run 30/30 hoặc lần lặp độc lập.** 5 lỗi 429 của lượt đầu vẫn được giữ và tính vào lịch sử độ ổn định/chi phí. Mean lượt đầu bị kéo xuống bởi các lỗi trả nhanh; không dùng để kết luận GPT-4o nhanh hơn. Pacing 15 giây giữa case chạy bù làm tăng thời gian cả batch; thời gian ngủ không nằm trong latency từng case, không phải latency UI/TTFT.

Preflight BOOK-05: 1/1 PASS, đúng `openai/gpt-4o`, receipt **{initial['new_preflight_known_cost_usd']:.8f} USD**. Tổng receipt đã biết cho preflight + lượt đầu + chạy bù: **{budget['known_cost_usd']:.9f} USD**, còn **{budget['missing_cost_cases']} case thiếu receipt**, nên đây là tổng tối thiểu đã quan sát, không phải hóa đơn đầy đủ. Receipt phủ 30 ID loại phần chi phí lần gọi lỗi và preflight; không dùng làm tổng chi phí rollout.

## Lỗi API và cách xử lý

OpenRouter trả `429`, `new-account-rpm/openai/gpt-4o`, `limit_source=openrouter_new_account`: hạn 20 requests/phút cho GPT-4o ở tài khoản này. Một case Agent gọi model nhiều lần, nên nghỉ 1 giây/case không đủ. Đây là lỗi giới hạn request, không phải bằng chứng model trả lời sai hay cần thay key.

- Lượt đầu: BOOK-05, BOOK-15, COST-11, REMINDER-03, REMINDER-05 lỗi 429; REMINDER-10, REMINDER-12, REMINDER-16 chưa chạy sau ngưỡng dừng 3 lỗi liên tiếp.
- Chạy bù 8 ID trong thư mục mới, giữ runtime/prompt/schema/dataset/scorer, chỉ tăng khoảng nghỉ từ 1 lên 15 giây/case. Không retry toàn bộ 30 câu để xóa lịch sử lỗi. Pacing giữa case không bảo đảm giới hạn từng model request cho mọi workload.
- Raw traces và lượt lỗi giữ nguyên. Không ghi đè `result.json`, `model_comparison.csv` hoặc producer cũ; kết quả bổ sung nằm ở `completion_result.json`, `recovery_summary.json`, `stage_comparison.csv`.

## Điều kiện và giới hạn đánh giá

30 ID development giống smoke Mistral/Gemma, gồm 8 Booking, 6 maintenance/cost, 5 reminder, 5 guardrail và 6 RAG. Dùng production graph với services SQLite/FakeRedis riêng; RAG tool là fixture. Token budget 2.048, temperature 0,2, timeout 60 giây, clock cố định, scorer 2.2; public schema và các điều kiện chung khớp. Không đo retrieval hoặc generation thật trong batch Agent này.

Routing Mistral ưu tiên `mistral/us,mistral/eu`, Gemma/GPT-4o tự động. Các run diễn ra tuần tự ở thời điểm khác nhau, UUID fixture khác nhưng cùng vai trò. Không khẳng định toàn bộ Agent requests giống từng byte. 45 kiểm tra offline được tái sử dụng vì source runtime/evaluator không đổi; Ruff các helper mới đạt.

Phủ GPT-4o: {covered['safety_violations']} safety violations theo detector, {covered['raw_argument_error_cases']} case lỗi raw arguments, {covered['truncated_cases']} truncation. Chỉ là kết quả các detector trong phạm vi đã chọn, không chứng nhận mọi câu trả lời đúng hoặc mọi yêu cầu booking an toàn. Audit raw proposal/calls nằm trong `completion_result.json`; runtime chặn/sửa không bị tính là model tự làm đúng. Semantic correctness vẫn `NOT_MEASURED`; các CSV review trống.

## Nhận xét chọn model và bước tiếp

Receipt phủ 30 ID của GPT-4o khoảng **{ratio:.1f} lần Mistral** trong các lượt này, chưa có nhãn độc lập chứng minh lợi ích nội dung tương ứng. Giữ Mistral làm baseline; Gemma là ứng viên giảm chi phí Agent nhưng chậm hơn trong smoke. GPT-4o ở nhóm dự phòng, cần pacing và bằng chứng chất lượng nếu muốn đưa vào shortlist nghiệm thu. `WRITE_MODEL` vẫn inactive.

Tiếp theo mục 7.4 đợt 2: khóa 30 query Rewrite từ bộ golden/v2.1 hiện có, điều kiện và rubric; pilot 3–5 query/model Mistral/Gemma/Gemini Flash Lite, rồi mới mở rộng nếu đạt. Chưa chạy Rewrite, generation GPT-4o, cấu hình ghép hoặc holdout ×3 trong đợt này. Review nguồn/nội dung vẫn tạm hoãn theo yêu cầu người dùng.

Kết quả cũ, dataset, corpus, source runtime và `.env` được kiểm hash trước/sau; xem `final_preservation.json` và file verification bên ngoài thư mục master. Không đổi cấu hình model ứng dụng.
"""
    with (MASTER / "report.md").open("x", encoding="utf-8") as stream:
        stream.write(report)
    with (MASTER / "report_controller.py").open("x", encoding="utf-8") as stream:
        stream.write((ROOT / "eval/step4_gpt4o_report.py").read_text(encoding="utf-8"))
    checks = {"previous": verify(read(MASTER / "protected_previous_files.json")),
              "corpus": verify(read(MASTER / "protected_corpus.json")), "source": verify(frozen_source()),
              "closed_initial_producers": verify(read(MASTER / "closed_initial_producer_hashes.json")),
              "recovery_controller_unchanged": digest(ROOT / "eval/step4_gpt4o_recovery.py") == plan["controller_sha256"],
              "env_unchanged": digest(ROOT / ".env") == manifest["env_sha256"], "review_labels": label_count}
    if not all(checks[key]["unchanged"] for key in ("previous", "corpus", "source", "closed_initial_producers")) or not checks["env_unchanged"] or not checks["recovery_controller_unchanged"]:
        raise RuntimeError("Preservation failed")
    write("final_preservation.json", checks)
    write("completed_producer_hashes.json", hashes([preflight, original, RECOVERY]))
    write("closed_master_hashes.json", hashes([MASTER]))
    final_checks = {"master": verify(read(MASTER / "closed_master_hashes.json")),
                    "producers": verify(read(MASTER / "completed_producer_hashes.json")), "preservation": checks}
    verification = ROOT / "eval/results/step4_agent_gpt4o_verification_20261008_15.json"
    with verification.open("x", encoding="utf-8") as stream:
        json.dump(final_checks, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"covered": covered, "new_known_spend_usd": budget["known_cost_usd"],
                      "missing_cost_cases": budget["missing_cost_cases"], "preservation": checks}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
