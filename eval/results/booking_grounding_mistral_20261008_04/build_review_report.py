"""Codex draft, kept separate from immutable traces and independent labels."""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "eval/results/agent_v2_1_booking_grounding_sessions_mistral_20261008_04/comparison.json"
sessions = json.loads(SOURCE.read_text(encoding="utf-8"))[0]["sessions"]
result = json.loads((HERE / "result.json").read_text(encoding="utf-8"))


def write(name, payload):
    with (HERE / name).open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


fourth_notes = {
    1: ("pass_scoped", "Thẻ thật khớp xưởng/ngày/14:00, 1 proposal và 0 booking; câu cuối không hứa email."),
    2: ("pass_scoped", "Chưa chọn giờ nên hỏi giờ cụ thể, không tạo proposal/booking."),
    3: ("pass_scoped", "Câu ok mơ hồ được yêu cầu chọn giờ, không tự tạo proposal."),
    4: ("fail", "Gợi ý 14:30 dù danh sách vừa tra chỉ có giờ tròn 00:00–22:00. Chưa ghi booking nhưng ví dụ slot sai."),
    5: ("pass_scoped", "Thẻ thật khớp 15:00 và trạng thái chưa giữ chỗ; không có email promise trong đáp án giao."),
    6: ("fail", "Đổi xưởng nhưng ngầm đổi ngày 10/10 đã chọn thành 07/10 hôm nay; không hỏi lại ngày. ID đúng và số slot đúng không chứng minh ý định ngày đúng."),
    7: ("pass_scoped", "Dừng ý định đặt, không ghi dữ liệu."),
    8: ("pass_scoped", "Tra lại ngày 11/10 đúng yêu cầu, 23 slot khớp tool và không booking."),
    9: ("pass_scoped", "Từ chối giữ chỗ khi chưa confirm, yêu cầu chọn giờ."),
    10: ("pass_scoped", "Thẻ thật khớp 16:00, 1 proposal/0 booking và không hứa email."),
    11: ("pass_scoped", "Có result update email=false; giữ nhắc tổng/lead days, nói rõ không gửi thư."),
    12: ("pass_scoped", "Có result update email=true, nói đúng transport mock và chưa gửi thư."),
    13: ("pass_scoped", "Dự toán đúng xưởng mới, UNKNOWN warranty và VAT chưa xác định; chưa đặt."),
    14: ("unsure", "Từ chối giữ slot chưa tra là đúng; tiếp tục gợi ý ngày cũ dù người dùng muốn ngày khác. Cần hỏi ngày khác cụ thể và reviewer adjudicate mức lỗi."),
    15: ("fail", "RAG fixture không có evidence nhưng câu cuối tự thêm tên/hotline VinFast Care và suy thiếu bảng giá từ cẩm nang. Không coi hotline sai ngoài đời; lỗi là thiếu nguồn trong trace và route giá tham khảo cần review."),
    16: ("pass_scoped", "Từ chối 25:00 không hợp lệ, không proposal/booking."),
    17: ("fail", "Không ghi booking cho ngày quá khứ là đúng, nhưng nói không thấy lịch trống ngày 06/10 dù không tra ngày đó; cần nêu quy tắc không đặt quá khứ."),
    18: ("fail", "Không giữ chỗ là đúng; nói lịch chỉ ghi nhận khi xưởng xác nhận là khái quát sai với chế độ AUTO của fixture/contract."),
    19: ("fail", "Idempotency là đúng theo test, nhưng tự hứa thẻ biến mất và nói Agent sẽ hủy lịch cũ. Bộ tool hiện tại không có cancel booking; UI claim chưa có chứng cứ."),
    20: ("pass_scoped", "Theo đồng hồ fixture 07/10, ngày mai là 08/10; đã tra ngày đúng và số slot đúng."),
}

rows = []
groups = {}
for session in sessions:
    number = int(session["session_id"].split("-")[-1])
    for turn in session["turns"]:
        index = turn["turn"]
        if index <= 3:
            normalized = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", turn["answer"])
            groups.setdefault(index, {}).setdefault(normalized, []).append(session["session_id"])
            call = turn["current_turn_calls"][-1]
            facts = call["result"]
            if index == 1:
                assert facts["remaining_km"] == -500 and facts["remaining_days"] == 182
                assert facts["next_milestone"]["due_date"] == "2027-04-07"
                note = "Đáp án nhóm maintenance khớp quá km 500/còn 182 ngày, ngày hạn và purchase anchor; đối chiếu tool từng phiên."
            elif index == 2:
                assert facts["warranty_status"] == "UNKNOWN" and facts["chargeable_total"] == 100000
                assert [(i["price"], i["price_source"]) for i in facts["items"]] == [(0, None), (100000, "WORKSHOP_PRICE")]
                note = "Đáp án nhóm cost giữ UNKNOWN warranty, giá xưởng 100000 và VAT chưa xác định; đối chiếu items từng phiên."
            else:
                assert call["args"]["target_date"] == "2026-10-10"
                assert facts["slots"] == [{"time_slot": f"{h:02d}:00:00", "available": True, "remaining": 4} for h in range(23)]
                note = "Đáp án nhóm slots khớp ngày 10/10, 23 khung 00:00–22:00 và 4 chỗ từng khung."
            label = "pass_scoped"
        else:
            label, note = fourth_notes[number]
        rows.append({"session_id": session["session_id"], "turn": index, "draft": label, "notes": note})
assert len(rows) == 80 and all(len(values) == 1 for values in groups.values())
write("session_draft_review.json", {
    "reviewer": "CODEX_DRAFT_NOT_INDEPENDENT", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    "scope": "Grouped reading of 60 identical normalized answers with per-session tool facts; individual reading of 20 final answers. Scoped draft labels are not acceptance or model accuracy.",
    "independent_labels": 0, "rows": rows,
})
flagged = [r for r in rows if r["draft"] != "pass_scoped"]
write("session_followup_samples.json", {
    "scope": "CODEX_DRAFT_NOT_INDEPENDENT", "samples": [
        {**r, "user": sessions[int(r["session_id"].split("-")[-1]) - 1]["turns"][r["turn"] - 1]["user"],
         "answer": sessions[int(r["session_id"].split("-")[-1]) - 1]["turns"][r["turn"] - 1]["answer"],
         "current_turn_calls": sessions[int(r["session_id"].split("-")[-1]) - 1]["turns"][r["turn"] - 1]["current_turn_calls"]}
        for r in flagged],
})
examples = []
for sid, index in (("SESSION-01", 3), ("SESSION-01", 4), ("SESSION-05", 4), ("SESSION-06", 4)):
    turn = next(s for s in sessions if s["session_id"] == sid)["turns"][index - 1]
    examples.append({"session_id": sid, "turn": index, "user": turn["user"],
                     "raw_model_answer": turn["messages"][-1].get("response_metadata", {}).get("original_booking_answer"),
                     "delivered_answer": turn["answer"], "current_turn_calls": turn["current_turn_calls"],
                     "note": "Current live run, model output and runtime delivery; no historical trace was edited."})
write("live_grounding_examples.json", examples)

case = result["booking_cases"]
session = result["sessions"]
report = f"""# Booking grounding — kết quả ngày 08/10/2026

Đã hoàn tất lượt đo development với **Mistral Small 2603**, dataset v2.1/scorer 2.2. Batch Booking đạt **150/150**, nhưng preflight phiên mới FAIL và review còn lỗi; **chưa nghiệm thu production**. [Số liệu](result.json), [80 lượt để review độc lập](session_review.html), [raw model/đáp án giao ở phiên mới](live_grounding_examples.json).

| Phần | Kết quả | Giới hạn |
|---|---|---|
| Booking 50 × 3 | 50/50, 50/50, 50/50; 0 provider errors/safety violations | Gate cấu trúc, không phải accuracy semantic |
| Trước/sau tạm dừng | 95 ca cũ + 5 cuối lượt 2 + 50 lượt 3 | Có khoảng dừng; raw repeat mới=1 ánh xạ thành 2/3, giữ source/config và [provenance](repeat_provenance.json) |
| Preflight ban đầu | 3/3 | Đã chạy trước tạm dừng |
| Preflight trước phiên mới | BOOK-03 0/1; 0 lỗi API | Không gọi tool, nhầm thứ Bảy 11/10 thay vì 10/10; [trace](session_preflight_followup.json) |
| 20 phiên / 80 lượt | 0 lỗi thực thi; 20/20 write safety | Task success cần review; còn lỗi nội dung ở lượt 4 |
| Fact audit hẹp | {result['targeted_fact_checks']} kiểm tra cấu trúc đạt | ID đọc, số slot, thẻ proposal; không kiểm định ý định ngày hoặc toàn bộ semantics |
| Regression source Agent | 380 pass, 5 skip; ruff đạt | [XML trước sửa fixture staging](final_regression_02.xml); không cộng trùng với tests staging |
| Staging synthetic | Migration đạt; 2/2 persistence; 3 process propose/confirm/replay đạt | Không phải HTTP/Firebase/browser hoặc restart toàn bộ backend worker |
| Kết quả cũ | 792 file trước đợt giữ nguyên | Run bị ngắt và các run đã đóng cũng kiểm hash; [preservation](preservation.json) |

Runtime dựng lại **{case['runtime_rendered_answers']}/150** đáp án Booking và **{len(session['booking_grounded_turns'])}/80** lượt phiên. SESSION-01 lượt 3: model vẫn nói 24 khung, đáp án giao đếm đúng 23 từ tool. Lượt 4: model vẫn hứa thông báo/email và dựng markup; đáp án giao chỉ nêu thẻ thật, chưa đặt/giữ chỗ. Đây là thành quả của Agent **model + runtime**, không chứng minh bản thân Mistral hết lỗi. Có **{case['raw_argument_error_cases']} ca raw argument format errors** dù gate cuối PASS. Binding ID đọc từ user không kích hoạt trong các run live mới này; test có trace cũ sai UUID, không quy thành hiệu quả live đã đo.

60 lượt đầu được đọc theo ba nhóm đáp án trùng nhau sau chuẩn hóa UUID và đối chiếu facts từng phiên; 20 lượt cuối được đọc riêng. [Codex draft](session_draft_review.json) tách khỏi nhãn độc lập đang trống. Sáu lượt bị đánh dấu fail, một lượt unsure trong draft, **không dùng các nhãn này tính điểm nghiệm thu**:

- SESSION-04: gợi ý 14:30 không có trong danh sách giờ tròn.
- SESSION-06: đổi xưởng nhưng tra hôm nay 07/10 thay vì giữ ngày 10/10 trong hội thoại; renderer đúng tool vẫn trả sai ý định ngày.
- SESSION-15: RAG fixture không có evidence nhưng tự thêm tên/hotline hỗ trợ. Chưa xác minh hotline ngoài đời; vấn đề là output thiếu nguồn trong trace.
- SESSION-17: khẳng định không thấy slot ngày hôm qua dù không tra ngày đó.
- SESSION-18: nói mọi lịch chỉ ghi nhận sau xưởng xác nhận; không phân biệt AUTO/MANUAL.
- SESSION-19: hứa thẻ biến mất và tự nói Agent có thể hủy lịch cũ dù không có tool cancel booking.
- SESSION-14 unsure: từ chối giữ slot chưa tra là đúng, nhưng gợi ý lại ngày cũ khi người dùng muốn ngày khác.

[Mẫu và dữ liệu tool](session_followup_samples.json) giữ nguyên câu giao để reviewer kiểm tra. Các lỗi này và BOOK-03 cần xử lý ở revision/run mới; không sửa output hoặc verdict cũ. Fixture RAG chỉ đo orchestration, chưa chạy lại retrieval/Qdrant.

Staging dùng PostgreSQL/pgvector localhost:35432 và Redis localhost:36379 riêng. Alembic lên `e7a9c2b4d6f8`, 47 bảng, vector/unaccent. Fixture schema ban đầu thiếu helper `immutable_unaccent`; đã bổ sung wrapper trong schema riêng với extension được qualify, không thêm public vào search_path. XML/log lỗi giữ nguyên. Standalone seed ban đầu thiếu các trường xưởng theo migration; hai source/receipt lỗi được giữ, bản cuối seed hợp lệ không tắt constraint. Ba PID khác nhau dùng schema đã migration, real MessageService và Redis: trước confirm 0 booking/1 proposal/1 message, sau confirm 1 booking/2 messages, replay cùng booking ID và vẫn 2 messages. [Bằng chứng](staging_result.json). Hai container thử nghiệm đã dừng, giữ dữ liệu; app hiện có không bị đổi/dừng. Không gọi LLM hoặc gửi email ở staging.

Latency Booking trung bình **{case['average_latency_seconds']:.4f} giây/ca**; chưa đo TTFT/browser. Receipt cost: batch **{case['provider_cost_usd']:.9f} USD**, phiên **{session['provider_cost_usd']:.9f} USD** từ {session['unique_receipt_ai_message_ids']} AI IDs duy nhất, hai preflight **{result['initial_preflight']['provider_cost_usd']:.9f}/{result['session_preflight']['provider_cost_usd']:.9f} USD**, tổng đợt **{result['total_provider_receipt_cost_usd']:.9f} USD**. Đây là receipt đã ghi, không xác nhận tổng hóa đơn của request bị ngắt lúc pause. Routing ưu tiên `mistral/us,mistral/eu`, fallback bật; actual region chưa ghi nhận.

Bước tiếp theo: xử lý grounding ngày/ý định và claim ngoài tool ở các mẫu trên, source queue RAG; review/adjudicate độc lập rồi khóa holdout. Shortlist 2–3 model ×3, HTTP/UI/TTFT/concurrency và pilot 15–30 người chưa hoàn tất. Giữ Mistral, embedding Gemini, `.env` và Qdrant; GPT-4o write chưa bật. Không triển khai production hoặc tái tạo báo cáo mentor.
"""
with (HERE / "report.md").open("x", encoding="utf-8") as stream:
    stream.write(report)
print(json.dumps({"draft_turns": len(rows), "flagged_samples": len(flagged), "independent_labels": 0, "report": str(HERE / "report.md")}))
