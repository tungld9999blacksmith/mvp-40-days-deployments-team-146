"""Build new review artifacts from completed runs; never overwrite an artifact."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESULTS = HERE.parent
BASELINE = "agent_v2_booking_10_mistral_routed_baseline_20261007_01"
BOOKING = "agent_v2_booking_50_mistral_routed_improved_20261007_01"
BUSINESS = "agent_v2_business_sessions_mistral_routed_20261007_01"
RAG = "rag_v2_full_100_mistral_routed_20261007_01"
SESSION_FIX = "agent_v2_session03_mistral_fixed_20261007_01"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(name):
    return [json.loads(line) for line in (RESULTS / name / "case_results.jsonl").read_text(encoding="utf-8").splitlines() if line]


def new_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def new_text(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(value)


def percentile(values, ratio):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(values) * ratio) - 1)] if ordered else None


def link(name, filename="report.md"):
    return f"[{name}](../{name}/{filename})"


def main():
    # Require finished outputs rather than publishing a partial run as complete.
    base = read_json(RESULTS / BASELINE / "comparison.json")[0]
    book = read_json(RESULTS / BOOKING / "comparison.json")[0]
    business = read_json(RESULTS / BUSINESS / "comparison.json")[0]
    rag = read_json(RESULTS / RAG / "metrics.json")
    session_fix = read_json(RESULTS / SESSION_FIX / "session_result.json")
    booking_rows, baseline_rows, business_rows, rag_rows = rows(BOOKING), rows(BASELINE), rows(BUSINESS), rows(RAG)
    baseline_ids = {row["case_id"] for row in baseline_rows}
    comparable = [row for row in booking_rows if row["case_id"] in baseline_ids]
    assert len(comparable) == len(baseline_rows) == 10
    same_case_pass = sum(row["metrics"]["task_passed"] for row in comparable)

    before = read_json(HERE / "manifest.json")["historical_files_before"]
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() if (ROOT / name).is_file() else None for name in before}
    changed = [name for name in before if before[name] != after[name]]
    assert not changed, changed
    preservation = {"unchanged": True, "files_verified": len(before), "changed": changed, "historical_files_after": after}
    new_json(HERE / "preservation.json", preservation)
    source_files = [path for folder in [ROOT / "backend/src/agents", ROOT / "backend/tests/evaluation_v2"] for path in folder.rglob("*.py") if "__pycache__" not in path.parts]
    source_files.extend([ROOT / "backend/src/modules/conversation/service.py", ROOT / ".github/workflows/agent-evaluation.yml", ROOT / "eval/datasets/agent_cases_v2.json"])
    new_json(HERE / "final_source_snapshot.json", {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "working_tree_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL)).hexdigest(),
        "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files},
        "note": "Final implementation snapshot; each live run keeps its own earlier manifest. Fingerprint includes pre-existing user edits; it does not attribute them to this implementation.",
    })

    latencies = [row["latency_seconds"] for row in rag_rows]
    rag_details = {
        **rag,
        "generation_provider_attempted": sum(bool(row["provider_events"]["generation"]) for row in rag_rows),
        "nonempty_answers": sum(bool(row["answer"].strip()) for row in rag_rows),
        "successful_end_to_end_rows": sum(not row["error"] and bool(row["answer"].strip()) for row in rag_rows),
        "answers_with_citations": sum(bool(row.get("response", {}).get("citations")) for row in rag_rows),
        "citation_id_membership_valid_rows": sum(row.get("citation_id_membership_valid", False) for row in rag_rows),
        "fallback_required_rows": sum(row.get("response", {}).get("fallback_required", False) for row in rag_rows),
        "average_latency_seconds": statistics.fmean(latencies) if latencies else None,
        "p50_latency_seconds": percentile(latencies, .50),
        "p90_latency_seconds": percentile(latencies, .90),
        "p95_latency_seconds": percentile(latencies, .95),
        "latency_percentile_method": "nearest rank, ceil(n * p)",
        "ttft": "NOT_MEASURED",
        "provider_cost_usd": "NOT_RECORDED_BY_RAG_USAGE_ADAPTER",
        "semantic_correctness": "NEEDS_HUMAN_REVIEW",
        "citation_claim_support": "NEEDS_HUMAN_REVIEW",
    }
    new_json(HERE / "rag_summary.json", rag_details)

    comparison = []
    for label, summary in [("baseline_booking_10", base), ("improved_booking_50", book), ("improved_business_70", business)]:
        for category, values in summary["categories"].items():
            comparison.append({"run": label, "model": summary["model"], "repeat": summary["repeat"], "category": category,
                               "passed": values["passed"], "attempted": values["total"], "selected_run": summary["selected"],
                               "complete_run": summary["complete"], "errors_run": summary["errors"], "safety_violations_run": summary["safety_violations"],
                               "average_latency_seconds_run": summary["average_latency_seconds"], "p95_latency_seconds_run": summary["p95_latency_seconds"],
                               "cost_usd_single_cases_run": summary["provider_cost_usd"], "semantic_review": "PENDING"})
    with (HERE / "model_comparison.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparison[0]))
        writer.writeheader()
        writer.writerows(comparison)
    # Run-level latency/cost are repeated for each category, not category estimates.
    with (HERE / "booking_before_after.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "baseline_pass", "improved_pass", "baseline_failures", "improved_failures"])
        improved_map = {row["case_id"]: row for row in comparable}
        for row in baseline_rows:
            after_row = improved_map[row["case_id"]]
            writer.writerow([row["case_id"], row["metrics"]["task_passed"], after_row["metrics"]["task_passed"], json.dumps(row["metrics"], ensure_ascii=False), json.dumps(after_row["metrics"], ensure_ascii=False)])

    tests = ElementTree.parse(HERE / "final_agent_booking_conversation_03.xml").getroot()
    suites = list(tests.iter("testsuite"))
    test_count = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    sessions = business["sessions"]
    session_errors = sum(bool(s["error"]) for s in sessions)
    session_safe = sum(not s["error"] and s["write_safety_passed"] for s in sessions)
    lines = [
        "# Kết quả triển khai và chạy lại Agent — 07/10/2026", "",
        "**Development evaluation, chưa nghiệm thu production.** Chạy trên `integration/main-real-services-email`, commit gốc `ac24213af4d1a3b1e432d506eee4afdcdabcfde2` và working tree đã sửa; fingerprint/source hashes của từng run nằm trong manifest. `.env` không được sửa bởi triển khai này.", "",
        "## Kết quả Mistral", "",
        "Giữ nguyên `mistralai/mistral-small-2603`. Sau cập nhật key của người dùng, endpoint mặc định vẫn trả 429; preflight ưu tiên `mistral/us`, `mistral/eu` trả 200 và các run chính bên dưới chạy được. Routing cho phép fallback, không đổi model ID. Không thay model trong cấu hình ứng dụng.", "",
        "| Tập development | Đạt mechanical gates | Lỗi provider/runtime | Vi phạm safety theo scorer |", "|---|---:|---:|---:|",
        f"| Booking baseline, 10 câu | {base['passed']}/10 | {base['errors']} | {base['safety_violations']} |",
        f"| Booking sau sửa, cùng 10 câu | {same_case_pass}/10 | {sum(bool(r['trace']['error']) for r in comparable)} | {sum(len(r['metrics']['safety_violations']) for r in comparable)} |",
        f"| Booking sau sửa, toàn bộ 50 câu | {book['passed']}/{book['selected']} | {book['errors']} | {book['safety_violations']} |",
    ]
    lines.extend(f"| {category} sau sửa | {values['passed']}/{values['total']} | xem run tổng | xem run tổng |" for category, values in business["categories"].items())
    lines.extend([
        "", f"Run business: {business['attempted']}/{business['selected']} câu được chạy, {business['errors']} lỗi, {business['safety_violations']} vi phạm safety theo scorer. Hội thoại: {len(sessions)}/20 phiên được ghi, {session_errors} lỗi; {session_safe}/{len(sessions)} phiên không lỗi và đạt kiểm tra booking-before-confirm/phát biểu thành công. **Task success nội dung các phiên chưa được human review.**", "",
        "SESSION-03 của lượt 20 phiên có lỗi nội dung: sau `ok`, model tự nêu 10:00 và trình bày thẻ bằng text dù không có proposal artifact (proposal_count=0). Safety scorer không bắt lỗi này vì chưa có booking/claim đã đặt. Đã thêm guardrail cho `ok` sau availability: yêu cầu chọn giờ; `ok` sau proposal thật: hướng dẫn bấm nút. Không áp dụng nhánh booking cho câu `ok` trong context reminder.", "",
        f"Đã chạy lại riêng SESSION-03 bằng đúng Mistral sau sửa: regression_passed={session_fix['regression_passed']}, 4 lượt không lỗi, không tạo proposal/booking và final answer yêu cầu chọn giờ. {link(SESSION_FIX)}. Lượt 20 phiên ban đầu vẫn giữ nguyên; chưa chạy lại toàn bộ 20 phiên hoặc chấm chúng là task success. Sửa này chỉ áp dụng history nhiều lượt, không tác động các case đơn đã benchmark Booking 50.", "",
        "Hai lỗi safety ở baseline là thiếu provenance/định dạng slot, không phải hai booking thật được ghi trái phép. BOOK-05 dùng giờ `14:00:00`; BOOK-06 gọi proposal thiếu availability; BOOK-08/09 chọn lệch ngày thứ trong tuần. Runtime sau sửa chuẩn hóa biểu diễn giờ tương đương, bổ sung prerequisite và giải ngày có căn cứ từ yêu cầu người dùng. Raw arguments trước sửa được giữ để phân biệt khả năng model với hiệu quả guardrail.", "",
        "BOOK-15 vẫn FAIL: yêu cầu **một xưởng** nhưng `find_workshops` nhận `limit=3` và trả hai xưởng. Không sửa expected để nâng tỷ lệ.", "",
        f"Booking 50 câu: latency trung bình **{book['average_latency_seconds']:.3f}s**, p95 **{book['p95_latency_seconds']:.3f}s**, cost do provider trả **${book['provider_cost_usd']:.6f}** cho toàn run. Chưa đo token đầu; đây không phải latency frontend. Thời gian seed/close fixture không tính, còn thời gian thực thi graph và đọc side effects có tính.", "",
        "Đối chứng 6/10 → 10/10 dùng cùng templates/clock/model/temperature/token budget/routing và cùng 9 tools/services. UUID fixture khác nhau theo run. Baseline là graph/prompt trước sửa với contracts hiện tại, không phải chạy lại benchmark cũ 6 tools. Chỉ một lần chạy trên development set; không suy ra chất lượng trên holdout hoặc ưu thế trước model khác.", "",
        "Tỷ lệ sau sửa đo **hệ thống Mistral + graph/guardrails**, không phải độ đúng model thô: runtime có thể sửa ngày/biểu diễn giờ và bổ sung prerequisite trước khi tool chạy. Raw argument errors và requested_tool_calls trong JSONL cho phép xem riêng lỗi model bị runtime sửa/chặn.", "",
        f"Raw/report: {link(BASELINE)}, {link(BOOKING)}, {link(BUSINESS)}. [Bảng trước/sau từng case](booking_before_after.csv), [CSV tổng hợp](model_comparison.csv). Các cột latency/cost/error ở CSV là số của phần câu đơn trong run, được lặp trên từng dòng category; không cộng chúng lại và không coi cost đó đã gồm 20 sessions.", "",
        "## Full RAG 100 câu", "",
        "Embedding: **Gemini `models/gemini-embedding-001`, 3072 chiều**; rewrite: **Mistral Small 2603**; generation: **`google/gemma-4-26b-a4b-it`**. Qdrant được đọc bằng adapter không tạo/re-index/clear collection. Cấu hình corpus, hash nội dung và reranker thực được lưu trong run. Không dùng LLM judge.", "",
        "Các model rewrite/generation được runner truyền tường minh. Checkout hiện tại chưa có factory `get_llm_provider_for_stage` mà default QueryRewriter tham chiếu; khi không inject provider, rewrite có thể chạy heuristic. Vì vậy run này chưa chứng minh production default dùng cùng cấu hình ba thành phần; cần đồng bộ dependency stage trước nghiệm thu deployment, không tự đổi model ứng dụng trong lượt rerun này.", "",
        f"- Đã chạy {rag['attempted']}/{rag['selected']} câu; {rag['errors']} lỗi, complete={rag['complete']}. Preflight error: `{rag['preflight_error']}`.",
        f"- Generation được gọi ở {rag_details['generation_provider_attempted']} câu; {rag_details['nonempty_answers']} câu có nội dung, {rag_details['successful_end_to_end_rows']} câu không lỗi và có nội dung.",
        f"- Document Hit@1: {rag['document_hit_at_1']:.1%}; Hit@3: {rag['document_hit_at_3']:.1%}; Hit@5: {rag['document_hit_at_5']:.1%}; MRR: {rag['document_mrr']:.4f}.",
        f"- {rag_details['answers_with_citations']}/{len(rag_rows)} câu có citation; {rag_details['citation_id_membership_valid_rows']}/{len(rag_rows)} dòng có mọi ID citation thuộc tập anchor truy xuất. Phép kiểm tra ID này có thể đúng với tập citation rỗng và **không chứng minh nguồn hỗ trợ nhận định**.",
        f"- {rag_details['fallback_required_rows']}/{len(rag_rows)} câu bật fallback_required. Correctness và citation claim support: **chờ human review**; chunk recall chưa đo vì chưa có golden chunk IDs.",
        f"- Latency p50/p90/p95: {rag_details['p50_latency_seconds']} / {rag_details['p90_latency_seconds']} / {rag_details['p95_latency_seconds']} giây (nearest rank). Chưa đo TTFT; RAG adapter chỉ lưu tokens, không có cost receipt để báo tổng chi phí đáng tin cậy.", "",
        "Hit được tính trên thứ tự 5 anchor chunks trước neighbor expansion, ở cấp document với mẫu số toàn bộ câu đã chạy, kể cả lỗi. Không coi Hit@5 là độ đúng câu trả lời. Câu trả lời trong full RAG là output pipeline riêng; chưa phải toàn bộ câu trả lời sau Agent orchestration và UI.", "",
        "Hai câu chưa hit document golden trong Top-5: **P01** (giá sạc tại nhà 3 kW, pipeline bật fallback) và **P11** (phí cứu hộ pin, lấy nguồn khác golden). P11 cần review liệu nguồn cứu hộ pin hiện có hỗ trợ đáp án; không tự đổi golden hoặc coi miss document là kết luận answer sai.", "",
        f"Evidence: {link(RAG)}, {link(RAG, 'case_results.jsonl')}, {link(RAG, 'human_review.csv')}, [tổng hợp RAG bổ sung](rag_summary.json), [ví dụ output thực](rag_answer_examples.md).", "",
        "## Thay đổi và xác minh", "",
        "- Graph dùng strict public schemas, prerequisite maintenance, provenance đúng xưởng/ngày/giờ và lỗi tool có kiểm soát. Prompt phân biệt proposal với booking đã confirm; chat `ok` không tự confirm booking.",
        "- RAG artifact giữ document/chunk IDs thật, confidence/fallback, không dựng citation. Chat persistence dùng completed answer của graph và lưu metadata RAG; token model đã stream trước khi guardrail sửa final answer vẫn cần kiểm tra trên UI.",
        "- Evaluator tách thiếu prerequisite/arguments/safety/answer khỏi tool đọc thừa; lưu raw requests, results, DB side effects, usage và review CSV. Mechanical PASS không chứng minh semantic correctness; bộ fixture VF6 và heuristic chữ/ngữ nghĩa còn hạn chế.",
        f"- Suite cuối: **{test_count - skipped - failed} PASS, {skipped} SKIP, {failed} FAIL/ERROR**. [JUnit](final_agent_booking_conversation_03.xml). Các suite trước có phần trùng, không cộng thành tổng test độc lập. Ruff và YAML parse đã qua.",
        f"- SHA-256 xác nhận **{len(before)} artifact trước triển khai không thay đổi**. [Manifest trước](manifest.json), [kiểm chứng sau](preservation.json). Không xóa/di chuyển/ghi đè lịch sử, không rescore bản gốc.", "",
        "## Hạn chế và quyết định model", "",
        "Tiếp tục dùng Mistral làm baseline đánh giá. Kết quả Booking đủ tốt để tiếp tục kiểm chứng, chưa đủ căn cứ đổi model ứng dụng hoặc xác nhận production readiness. Các lượt Gemma/GPT-4o trước dùng phiên bản guardrail khác hoặc bị 401 sau xoay key, nên không xếp hạng chúng với Mistral 49/50 như một đối chứng công bằng. Chưa chạy đủ 2–3 model × 3 lần trên holdout độc lập.", "",
        "Các lượt 429/401 và lượt có lỗi SDK routing được giữ nguyên. Run full RAG Gemma rewrite cũ có 82/100 lỗi sau credential rotation; run Booking shortlist 50 câu cũng bị 401. Không loại các lỗi khỏi báo cáo gốc hoặc dùng những run đó kết luận model kém về nội dung. Lượt shortlist bị ngắt chỉ có một dòng JSONL được đánh dấu incomplete trong index.", "",
        "Còn cần review độc lập dataset/đáp án/citation, đánh giá Agent final answer với retrieval staging, PostgreSQL/Redis với migration thật và restart worker, UI confirm/concurrency, TTFT và thử 15–30 người. SQLite/FakeRedis engine/session mới đã được kiểm tra; Docker daemon local chưa sẵn sàng nên không tự dùng database production. CI staging đã chuẩn bị nhưng chưa chạy; test đó chưa thay thế bằng chứng migration/worker/UI.", "",
        "Không cộng 120 câu nghiệp vụ Agent với 100 câu pipeline RAG để báo Agent 220/220 end-to-end. Dataset 220 + 20 phiên được tạo nhưng chưa khóa thành bộ nghiệm thu.", "",
        "## Các ca còn trượt trong lượt business", "",
    ])
    failures = [row for row in business_rows if not row["metrics"]["task_passed"]]
    if not failures:
        lines.append("Không có ca trượt mechanical gates trong lượt business; vẫn chờ review nội dung.")
    for row in failures:
        reasons = {key: value for key, value in row["metrics"].items() if key in {"required_tools_missing", "dependency_errors", "argument_errors", "safety_violations", "answer_errors"} and value}
        lines.extend([f"- **{row['case_id']}** — {row['user']}", f"  Lý do tự động: `{json.dumps(reasons, ensure_ascii=False)}`"])
        if row["case_id"] == "MAINT-07":
            lines.append("  Model trả ODO 12.500 km từ trusted vehicle context, không gọi maintenance. Đây là FAIL theo required-tool gate hiện tại; chưa chứng minh câu trả lời ODO sai. Cần review độc lập xem tool có thực sự bắt buộc trong case này; không thay expected sau chạy để nâng điểm.")
        if row["case_id"] == "REMINDER-10":
            lines.append("  Dataset yêu cầu update trong ca lead_days=31 không hợp lệ. Model chỉ đọc cấu hình và hỏi lại, không giải thích rõ giới hạn. Cần sửa thiết kế ca trong phiên bản dataset tiếp theo để chấm từ chối input sai và không mutation; không nới gate/rescore run này.")
        if row["case_id"] == "REMINDER-17":
            lines.append("  Model chỉ gửi reminder_lead_days=7; fixture đã có reminders_enabled=True. Vì expected yêu cầu truyền tường minh reminders_enabled=True, gate arguments vẫn FAIL dù trạng thái sau update có thể đúng. Cần bổ sung fixture đang tắt và chấm side effect trạng thái, không suy ra mất chức năng bật nhắc chỉ từ ca này.")
    new_text(HERE / "report.md", "\n".join(lines) + "\n")

    examples = ["# Một số câu trả lời full RAG thực tế", "", "Output chưa được chấm semantic/citation bằng human review. Đối chiếu toàn bộ 100 câu trong JSONL và review CSV của run.", ""]
    misses = [row for row in rag_rows if not set(row["expected_doc_ids"]) & set(row["ranked_doc_ids"])]
    selected_examples = rag_rows[:3] + misses[:2] if len(misses) >= 2 else rag_rows[:5]
    for row in selected_examples:
        citations = row.get("response", {}).get("citations", [])
        examples.extend([f"## {row['case_id']}", "", f"**Câu hỏi:** {row['question']}", "", f"**Đáp án golden:** {row['expected_answer']}", "", "**Câu trả lời thực:**", "", row["answer"], "", f"**Lỗi:** {row['error']}; confidence: {row.get('response', {}).get('confidence')}; fallback: {row.get('response', {}).get('fallback_required')}", "", "**Nguồn được trả về:**", "", "```json", json.dumps(citations, ensure_ascii=False, indent=2), "```", ""])
    new_text(HERE / "rag_answer_examples.md", "\n".join(examples))
    index = ["# Kết quả đánh giá Agent / RAG", "", "Các run ngày 07/10/2026 dùng dataset development; chưa phải nghiệm thu production. Kết quả lịch sử giữ nguyên.", "", "## Kết quả chính sau cập nhật OpenRouter", "",
             f"- [Báo cáo tổng hợp]({HERE.name}/report.md): Booking Mistral {book['passed']}/{book['selected']}; cùng 10 câu trước/sau {base['passed']}/10 → {same_case_pass}/10; các nhóm business, sessions, full RAG và giới hạn phép chấm.",
             f"- [Booking 50 câu]({BOOKING}/report.md) · [baseline 10 câu]({BASELINE}/report.md) · [business + sessions]({BUSINESS}/report.md).",
             f"- [Full RAG 100 câu]({RAG}/report.md) · [ví dụ câu trả lời]({HERE.name}/rag_answer_examples.md) · [review CSV]({RAG}/human_review.csv).",
             f"- [Bảo toàn {len(before)} artifact cũ]({HERE.name}/preservation.json) · [JUnit cuối]({HERE.name}/final_agent_booking_conversation_03.xml) · [Sửa lỗi ok tự chọn giờ]({SESSION_FIX}/report.md).", "", "## Lịch sử và run dùng chẩn đoán", "",
             "Bảng 10 model cũ: [benchmark report](../../backend/tests/test_agents/evaluationLLM/results/benchmark_report.md). Contract/scorer cũ khác runtime hiện tại; không xếp hạng chung với các run v2. [Rà soát Booking](booking_review_20261007_121335_fe5d12/report.md). `report.md` lịch sử tại thư mục này vẫn giữ nguyên.", "", "| Run | Trạng thái artifact |", "|---|---|"]
    for folder in sorted(RESULTS.iterdir()):
        if not folder.is_dir() or folder == HERE or not (folder / "manifest.json").exists():
            continue
        target = "report.md" if (folder / "report.md").exists() else "manifest.json"
        description = "Completed artifacts; xem errors/complete trong báo cáo, không mặc định là PASS" if target == "report.md" else "Incomplete/interrupted; không dùng làm kết quả chất lượng"
        if read_json(folder / "manifest.json").get("kind") == "model_preflight":
            target = "preflight.json" if (folder / "preflight.json").exists() else "manifest.json"
            description = "Preflight endpoint/completion; không phải benchmark chất lượng"
        if folder.name in {BASELINE, BOOKING, BUSINESS, RAG, SESSION_FIX}:
            description = "Run chính; review nội dung chưa hoàn tất"
        index.append(f"| [{folder.name}]({folder.name}/{target}) | {description} |")
    new_text(RESULTS / "README.md", "\n".join(index) + "\n")
    print(json.dumps({"report": str(HERE / 'report.md'), "preserved": len(before), "booking_passed": book['passed'], "rag_attempted": rag['attempted'], "business_passed": business['passed'], "session_errors": session_errors}))


if __name__ == "__main__":
    main()
