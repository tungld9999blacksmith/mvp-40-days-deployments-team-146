# RAG Evaluation Report

**Ngày đánh giá:** 2026-10-02 (Asia)
**Backend:** Qdrant Cloud — `ev_care_knowledge_base_staging` (819 chunks, 28 doc_ids)
**Pipeline:** Gemini/Qdrant dense + BM25 → HeuristicReranker; heuristic query rewriter; `gemini-3.5-flash-lite` generator; Top-K=3
**Golden Set:** `golden_set.jsonl`, 100 câu hỏi, 6 category
**Chế độ:** Kết quả retrieval production trên 100 câu. Generation được chạy lại trên 18 câu (3 câu/category) bằng `gemini-3.5-flash-lite`; 18/18 câu có output Gemini thật.

---

## 1. Corpus Audit

| Thông tin | Giá trị |
|-----------|---------|
| Nguồn | Qdrant Cloud `ev_care_knowledge_base_staging` |
| Tổng chunks | 819 |
| Doc_ids | 28 |
| Query có ít nhất một relevant indexed document | 100/100 |
| Tất cả relevant_doc_ids đều có trong Qdrant | 100/100 |
| Expected keywords được indexed evidence hỗ trợ | 100/100 |
| Expected answers được indexed evidence hỗ trợ | 100/100 |

**Phân phối category trong corpus Qdrant:**

| Category | Chunks | % |
|----------|--------|---|
| general | 257 | 31.4% |
| warranty | 299 | 36.5% |
| battery | 116 | 14.2% |
| maintenance | 73 | 8.9% |
| procedure | 48 | 5.9% |
| pricing | 26 | 3.2% |

Audit bổ sung: model compatibility đạt 100/100; category compatibility đạt 99/100. G03 là trường hợp duy nhất có category metadata không tương thích.

---

## 2. Metric A — Retrieval Quality

| Chỉ số | Giá trị | Target | Đạt? |
|--------|---------|--------|------|
| **hit_at_1** | 0.8500 | 0.70 | ✅ |
| **hit_at_3** | 0.9600 | 0.80 | ✅ |
| **hit_at_5** | 0.9600 | 0.85 | ✅ |
| **mrr** | 0.9017 | 0.75 | ✅ |
| **ctx_precision** | 0.6300 | 0.70 | ⚠️ |
| **ctx_recall** | 0.8283 | 0.70 | ✅ |
| **keyword coverage** | 0.8875 | 0.70 | ✅ |
| **retrieval pass rate** | 89.0% (89/100) | 80% | ✅ |
| avg_latency_ms | 2811.6 | — | — |
| p95_latency_ms | 3281.2 | — | — |

**Metric A theo Category:**

| Category | N | Pass rate | Hit@3 | Avg score |
|----------|---|-----------|-------|-----------|
| battery ✅ | 20 | 90.0% | 100.0% | 0.8574 |
| general ✅ | 4 | 100.0% | 100.0% | 0.8563 |
| maintenance ✅ | 26 | 92.3% | 100.0% | 0.8097 |
| pricing ✅ | 16 | 100.0% | 100.0% | 0.8449 |
| procedure ✅ | 14 | 85.7% | 92.9% | 0.8161 |
| warranty ⚠️ | 20 | 75.0% | 85.0% | 0.8168 |

---

## 3. Answer Quality — Gemini 3.5 Flash Lite

Đã đánh giá 18 câu có output thật từ `gemini-3.5-flash-lite`, gồm 3 câu cho mỗi category. Answer coverage của mẫu là 100% (18/18).

| Chỉ số | Giá trị | Trạng thái |
|--------|---------|------------|
| Correctness | 0.6833 | đã đo trên 18 câu |
| Completeness | 0.8333 | đã đo trên 18 câu |
| Answer relevancy | 0.8514 | đã đo trên 18 câu |
| Coherence | 1.0000 | đã đo trên 18 câu |
| Citation correctness | 0.6944 | đã đo trên 18 câu |
| Citation support | 0.7222 | đã đo trên 18 câu |

---

## 4. Phân tích điểm nghẽn

### 4.1 Context Precision còn thấp
Context precision đạt 63.0%, vẫn dưới target 70%. Production retrieval thường trả thêm nguồn đúng chủ đề nhưng không nằm trong `relevant_doc_ids`, nên Hit@3 đạt 96.0% trong khi precision chưa đạt.

### 4.2 Warranty và Procedure
Warranty có pass rate 75.0%, dưới target 80%; procedure đạt 85.7%. Đây là hai nhóm cần tiếp tục rà soát metadata và danh sách relevant sources. Battery đạt 90.0%, maintenance đạt 92.3% và pricing đạt 100.0%.

### 4.3 Generation sample
Gemini 3.5 Flash Lite hoàn thành 18/18 câu mà không gặp lỗi model hoặc quota. Answer relevancy đạt 85.14% và coherence đạt 100%; citation correctness đạt 69.44% và citation support đạt 72.22%, cho thấy phần trích dẫn vẫn là điểm cần cải thiện.

---

## 5. Kết Luận

| Chỉ số | Giá trị | Target | Đạt? |
|--------|---------|--------|------|
| hit_at_1 | 0.8500 | 0.70 | ✅ |
| hit_at_3 | 0.9600 | 0.80 | ✅ |
| hit_at_5 | 0.9600 | 0.85 | ✅ |
| mrr | 0.9017 | 0.75 | ✅ |
| ctx_precision | 0.6300 | 0.70 | ⚠️ |
| ctx_recall | 0.8283 | 0.70 | ✅ |
| keyword_coverage | 0.8875 | 0.70 | ✅ |
| retrieval pass rate | 0.8900 | 0.80 | ✅ |
| Answer quality | measured on 18/18 | 18/18 sampled answers | ✅ |

**Đánh giá:** Các chỉ số retrieval production. `gemini-3.5-flash-lite` hoàn thành 100% mẫu generation; câu trả lời có relevancy và coherence tốt, còn citation correctness và citation support cần được cải thiện.

---

## 6. Chi Tiết Kết Quả Production Mới Nhất

| ID | Category | Model | Score | H@3 | KwCov | Faith | AnsR | Cite | Thiếu keywords |
|----|----------|-------|-------|-----|-------|-------|------|------|----------------|
| M01   | maintenance | VF8      | 0.775 | ✅ | 1.00 | — | 0.85 | 1.00 | — |
| M02   | maintenance | VFe34    | 0.801 | ✅ | 1.00 | — | 1.00 | 1.00 | — |
| M03   | maintenance | ALL      | 0.864 | ✅ | 1.00 | — | 0.92 | 1.00 | — |
| M04   | maintenance | VFe34    | 0.814 | ✅ | 1.00 | — | — | — | — |
| M05   | maintenance | ALL      | 0.793 | ✅ | 1.00 | — | — | — | — |
| M06   | maintenance | VF3      | 0.746 | ✅ | 0.67 | — | — | — | 15.000 |
| M07   | maintenance | VFe34    | 0.841 | ✅ | 1.00 | — | — | — | — |
| M08   | maintenance | VFe34    | 0.850 | ✅ | 1.00 | — | — | — | — |
| M09   | maintenance | VF8      | 0.749 | ✅ | 1.00 | — | — | — | — |
| M10   | maintenance | ALL      | 0.848 | ✅ | 0.33 | — | — | — | dài hơn, truyền động đơn giản |
| M11   | maintenance | VFe34    | 0.831 | ✅ | 1.00 | — | — | — | — |
| M12   | maintenance | VFe34    | 0.857 | ✅ | 1.00 | — | — | — | — |
| M13   | maintenance | VF8      | 0.734 | ✅ | 1.00 | — | — | — | — |
| M14   | maintenance | VFMPV7   | 0.761 | ✅ | 1.00 | — | — | — | — |
| M15   | maintenance | ALL      | 0.883 | ✅ | 1.00 | — | — | — | — |
| M16   | maintenance | ALL      | 0.836 | ✅ | 1.00 | — | — | — | — |
| M17   | maintenance | VFe34    | 0.821 | ✅ | 1.00 | — | — | — | — |
| M18   | maintenance | VFe34    | 0.818 | ✅ | 1.00 | — | — | — | — |
| M19   | maintenance | VFe34    | 0.826 | ✅ | 1.00 | — | — | — | — |
| M20   | maintenance | VFe34    | 0.819 | ✅ | 1.00 | — | — | — | — |
| M21   | pricing     | ALL      | 0.802 | ✅ | 1.00 | — | 0.80 | 0.00 | — |
| M22   | maintenance | VFe34    | 0.817 | ✅ | 1.00 | — | — | — | — |
| M23   | maintenance | VFe34    | 0.831 | ✅ | 0.67 | — | — | — | dung dịch làm mát |
| M24   | maintenance | VFe34    | 0.848 | ✅ | 1.00 | — | — | — | — |
| M25   | maintenance | ALL      | 0.743 | ✅ | 1.00 | — | — | — | — |
| W01   | warranty    | VF8      | 0.845 | ✅ | 1.00 | — | 0.67 | 1.00 | — |
| W02   | warranty    | VF6      | 0.859 | ✅ | 1.00 | — | 0.75 | 0.00 | — |
| W03   | warranty    | VF3      | 0.854 | ✅ | 1.00 | — | 0.75 | 1.00 | — |
| W04   | warranty    | ALL      | 0.568 | ✅ | 0.67 | — | — | — | xưởng dịch vụ |
| W05   | warranty    | ALL      | 0.796 | ✅ | 1.00 | — | — | — | — |
| W06   | warranty    | VF8      | 0.778 | ✅ | 0.33 | — | — | — | xưởng dịch vụ, ủy quyền |
| W07   | warranty    | ALL      | 0.713 | ❌ | 0.50 | — | — | — | 70% |
| W08   | warranty    | ALL      | 0.888 | ✅ | 0.67 | — | — | — | va chạm |
| W09   | warranty    | VFMPV7   | 0.858 | ✅ | 1.00 | — | — | — | — |
| W10   | warranty    | ALL      | 0.852 | ✅ | 0.67 | — | — | — | 20.000 |
| W11   | warranty    | VF7      | 0.851 | ✅ | 1.00 | — | — | — | — |
| W12   | warranty    | ALL      | 0.820 | ✅ | 1.00 | — | — | — | — |
| W13   | warranty    | ALL      | 0.694 | ❌ | 0.50 | — | — | — | loại trừ |
| W14   | warranty    | VFe34    | 0.841 | ✅ | 1.00 | — | — | — | — |
| W15   | warranty    | VF8      | 0.891 | ✅ | 1.00 | — | — | — | — |
| W16   | warranty    | VF6      | 0.885 | ✅ | 1.00 | — | — | — | — |
| W17   | warranty    | ALL      | 0.831 | ❌ | 0.67 | — | — | — | xưởng dịch vụ |
| W18   | warranty    | VF8      | 0.806 | ✅ | 1.00 | — | — | — | — |
| W19   | warranty    | VF5      | 0.864 | ✅ | 1.00 | — | — | — | — |
| W20   | warranty    | VF3      | 0.842 | ✅ | 1.00 | — | — | — | — |
| B01   | battery     | ALL      | 0.833 | ✅ | 1.00 | — | 0.42 | 1.00 | — |
| B02   | battery     | VF8      | 0.912 | ✅ | 1.00 | — | 0.88 | 1.00 | — |
| B03   | battery     | VF6      | 0.766 | ✅ | 0.00 | — | 0.43 | 0.00 | 1900 23 23 89, 50.000 VNĐ, 15 phút |
| B04   | battery     | VFe34    | 0.897 | ✅ | 0.67 | — | — | — | không lạm dụng |
| B05   | battery     | ALL      | 0.853 | ✅ | 1.00 | — | — | — | — |
| B06   | battery     | ALL      | 0.914 | ✅ | 1.00 | — | — | — | — |
| B07   | battery     | VF5      | 0.772 | ✅ | 1.00 | — | — | — | — |
| B08   | battery     | VF7      | 0.710 | ✅ | 0.50 | — | — | — | nhiệt độ |
| B09   | battery     | VF3      | 0.906 | ✅ | 1.00 | — | — | — | — |
| B10   | battery     | ALL      | 0.889 | ✅ | 1.00 | — | — | — | — |
| B11   | battery     | ALL      | 0.873 | ✅ | 0.33 | — | — | — | 24/7, 50.000 |
| B12   | battery     | ALL      | 0.896 | ✅ | 1.00 | — | — | — | — |
| B13   | battery     | VF3      | 0.758 | ✅ | 1.00 | — | — | — | — |
| B14   | battery     | VF8      | 0.869 | ✅ | 0.75 | — | — | — | 31 phút |
| B15   | battery     | ALL      | 0.950 | ✅ | 1.00 | — | — | — | — |
| B16   | battery     | VFe34    | 0.877 | ✅ | 1.00 | — | — | — | — |
| B17   | battery     | VF6      | 0.767 | ✅ | 0.50 | — | — | — | 0% |
| B18   | battery     | ALL      | 0.861 | ✅ | 1.00 | — | — | — | — |
| B19   | battery     | ALL      | 0.923 | ✅ | 1.00 | — | — | — | — |
| B20   | battery     | VF7      | 0.920 | ✅ | 1.00 | — | — | — | — |
| P01   | pricing     | ALL      | 0.861 | ✅ | 1.00 | — | 1.00 | 1.00 | — |
| P02   | pricing     | ALL      | 0.858 | ✅ | 1.00 | — | 1.00 | 1.00 | — |
| P03   | pricing     | ALL      | 0.852 | ✅ | 1.00 | — | — | — | — |
| P04   | pricing     | ALL      | 0.941 | ✅ | 1.00 | — | — | — | — |
| P05   | pricing     | VF5      | 0.768 | ✅ | 1.00 | — | — | — | — |
| P06   | pricing     | VF5      | 0.854 | ✅ | 1.00 | — | — | — | — |
| P07   | pricing     | VF5      | 0.806 | ✅ | 1.00 | — | — | — | — |
| P08   | pricing     | VF5      | 0.758 | ✅ | 1.00 | — | — | — | — |
| P09   | pricing     | VF5      | 0.858 | ✅ | 1.00 | — | — | — | — |
| P10   | pricing     | VF8      | 0.812 | ✅ | 1.00 | — | — | — | — |
| P11   | pricing     | ALL      | 0.904 | ✅ | 1.00 | — | — | — | — |
| P12   | pricing     | VF8      | 0.865 | ✅ | 1.00 | — | — | — | — |
| P13   | pricing     | VF8      | 0.849 | ✅ | 1.00 | — | — | — | — |
| P14   | pricing     | VF8      | 0.854 | ✅ | 1.00 | — | — | — | — |
| P15   | pricing     | ALL      | 0.877 | ✅ | 1.00 | — | — | — | — |
| PR01  | procedure   | ALL      | 0.839 | ✅ | 0.67 | — | 1.00 | 1.00 | app |
| PR02  | procedure   | ALL      | 0.607 | ✅ | 0.67 | — | 1.00 | 0.00 | phê duyệt |
| PR03  | procedure   | ALL      | 0.886 | ✅ | 0.67 | — | 1.00 | 1.00 | lỗi |
| PR04  | procedure   | ALL      | 0.798 | ✅ | 0.00 | — | — | — | email, nhắc nhở |
| PR05  | procedure   | ALL      | 0.834 | ✅ | 0.67 | — | — | — | tận nơi |
| PR06  | procedure   | ALL      | 0.771 | ✅ | 1.00 | — | — | — | — |
| PR07  | procedure   | ALL      | 0.835 | ✅ | 0.67 | — | — | — | 24/7 |
| PR08  | procedure   | ALL      | 0.697 | ✅ | 1.00 | — | — | — | — |
| PR09  | procedure   | ALL      | 0.904 | ✅ | 1.00 | — | — | — | — |
| PR10  | procedure   | ALL      | 0.822 | ✅ | 1.00 | — | — | — | — |
| PR11  | procedure   | ALL      | 0.869 | ✅ | 1.00 | — | — | — | — |
| PR12  | procedure   | ALL      | 0.843 | ✅ | 1.00 | — | — | — | — |
| G01   | maintenance | ALL      | 0.777 | ✅ | 1.00 | — | — | — | — |
| G02   | general     | ALL      | 0.845 | ✅ | 1.00 | — | 1.00 | 0.50 | — |
| G03   | general     | ALL      | 0.760 | ✅ | 1.00 | — | 1.00 | 1.00 | — |
| G04   | general     | VF8      | 0.902 | ✅ | 1.00 | — | 0.88 | 0.00 | — |
| G05   | maintenance | ALL      | 0.768 | ✅ | 0.33 | — | — | — | dài hơn, truyền động đơn giản |
| G06   | procedure   | ALL      | 0.810 | ✅ | 1.00 | — | — | — | — |
| G07   | procedure   | ALL      | 0.912 | ❌ | 1.00 | — | — | — | — |
| G08   | general     | ALL      | 0.918 | ✅ | 0.67 | — | — | — | app |

`AnsR` và `Cite` được điền cho 18 câu thuộc mẫu generation. `Faith` giữ `—` ở bảng chi tiết vì runner hiện chỉ lưu citation support ở mức tổng hợp; citation support của toàn mẫu là 0.7222.

---

