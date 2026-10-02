# Phân tích lỗi RAG Qdrant

## Kết luận

Pipeline production dùng Qdrant, không dùng Chroma. Script đánh giá cũ đã
được thay bằng Qdrant + BM25 + reranker và bộ 42 câu hỏi có
`source_evidence` trỏ trực tiếp vào `data/knowledge/raw`.

Collection mới `ev_care_knowledge_base_staging` có 918 point. `.env` hiện trỏ
tới collection này; collection cũ 751 point vẫn được giữ để rollback.

## Vấn đề của baseline

1. `run_eval.py` dùng Chroma nên không đo pipeline production.
2. Golden set cũ chứa nhiều claim không có trong raw: bảng giá bảo dưỡng
   giả lập, Turtle Mode, một số mốc SOH và hạng mục bảo dưỡng suy diễn.
3. FAQ bị gán category `procedure` từ 1.000 ký tự đầu, làm 394/751
   chunk mang nhãn `procedure`; chỉ 18 chunk mang nhãn `battery`.
4. Model có khoảng trắng (`VF 8`, `VF e34`, `VF MPV 7`) không được nhận
   diện chính xác. Tài liệu `_ALL` có thể bị gán nhầm cho một model.
5. Hard filter category loại bỏ các FAQ đa chủ đề.
6. Policy bảo hành hiện hành bằng tiếng Anh có thể mâu thuẫn với
   FAQ/manual tiếng Việt cũ; reranker cũ không có source authority.
7. Câu trả lời đủ ý có thể bị chia qua hai chunk kề nhau.

## Thay đổi đã thực hiện

- Suy luận metadata theo tên file và section; nhận diện model có/không có
  khoảng trắng; `_ALL` và FAQ mặc định model `ALL`.
- Dense retrieval không hard-filter category; BM25 giữ nhánh filter và nhánh
  fallback, hợp nhất bằng RRF.
- BM25 mở rộng thuật ngữ Việt–Anh cho warranty policy.
- Heuristic reranker kết hợp dense, sparse, RRF, lexical coverage và source
  authority; policy hiện hành được ưu tiên hơn FAQ cũ.
- Bổ sung chunk liền kề sau rerank để tăng completeness/coherence.
- Thêm `knowledge/derived/warranty_policy_vi.md`, là bản chuẩn hóa có
  truy vết từ `warranty_policy_ALL.md`.
- Generator được thêm quy tắc xử lý xung đột nguồn, tính đủ và
  mạch lạc.
- Thêm script re-index raw trực tiếp vào Qdrant, không trung chuyển qua
  Chroma.

## Kết quả

### Baseline Qdrant cũ, 751 point

- Hit@1: 78,6%
- Hit@3: 85,7%
- MRR: 0,8175
- Evidence coverage: 76,2%
- Grounded pass theo metric cũ: 73,8%

### Staging sau re-index, trước dataset warranty chuẩn hóa

- Hit@1: 81,0%
- Hit@3: 85,7%
- MRR: 0,8333
- Avg top cosine: 0,8744
- Evidence coverage: 77,8%
- P95 retrieval có Gemini API: 1.910 ms

### Audit cuối trên staging 918 point

Do quota `gemini-embedding-001` free tier đã hết sau khi embed 907 chunk và
chạy hai vòng eval, vòng cuối dùng nhánh Qdrant payload + BM25 + reranker +
neighbor expansion, không gọi thêm query embedding:

- Source hit Top-5: **100,0%**
- Evidence coverage: **90,5%**
- Grounded pass: **90,5%**
- Maintenance: 8/8
- Warranty: 10/10
- Battery: 9/10
- Pricing: 3/4
- Procedure: 5/6
- General: 4/4

Kết quả vượt ngưỡng grounded pass 80%. Tuy nhiên, latency Qdrant + Gemini
embedding hiện chưa đạt mục tiêu 500 ms và full hybrid eval cuối cần chạy
lại sau khi quota embedding reset.

## Chạy lại

```bash
.venv/bin/python backend/tests/test_agents/test_rag/evaluation/run_eval.py
```

Re-index an toàn vào staging:

```bash
.venv/bin/python backend/scripts/reindex_qdrant_from_raw.py \
  --collection ev_care_knowledge_base_staging --replace
```
