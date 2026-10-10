# Một số câu trả lời full RAG thực tế

Output chưa được chấm semantic/citation bằng human review. Đối chiếu toàn bộ 100 câu trong JSONL và review CSV của run.

## M01

**Câu hỏi:** Bảo dưỡng định kỳ mốc 15.000 km xe VF8 gồm những hạng mục gì?

**Đáp án golden:** Mốc 15.000 km xe VF8 cần: kiểm tra OBD và BMS pin, kiểm tra mức dung dịch làm mát pin, kiểm tra má phanh và áp suất lốp, bổ sung nước rửa kính.

**Câu trả lời thực:**

Hiện tài liệu chính hãng chưa có thông tin chi tiết về danh sách các hạng mục bảo dưỡng cụ thể cho mốc 15.000 km đối với dòng xe VF8. Các tài liệu hiện có chỉ cung cấp thông tin về mốc bảo dưỡng định kỳ mới cho ô tô điện là 15.000 km hoặc 1 năm (tùy điều kiện nào đến trước) [Tài liệu 1] và lịch bảo dưỡng của dòng xe Fadil (xe xăng) . 

Để biết chính xác các hạng mục cần kiểm tra hoặc thay thế cho xe VF8 tại mốc 15.000 km, Quý khách vui lòng liên hệ trực tiếp với xưởng dịch vụ VinFast hoặc đặt lịch hẹn để kỹ thuật viên kiểm tra và tư vấn cụ thể.

**Lỗi:** None; confidence: low; fallback: True

**Nguồn được trả về:**

```json
[
  {
    "document_id": "toi_uu_moc_bao_duong_ALL",
    "title": "VINFAST TỐI ƯU MỐC BẢO DƯỠNG, GIẢM CHI PHÍ VẬN HÀNH CHO KHÁCH HÀNG",
    "section": "VINFAST TỐI ƯU MỐC BẢO DƯỠNG, GIẢM CHI PHÍ VẬN HÀNH CHO KHÁCH HÀNG",
    "source_url": null,
    "chunk_id": "toi_uu_moc_bao_duong_ALL_chk_0001",
    "score": 0.9996
  }
]
```

## M02

**Câu hỏi:** Pin chìa khóa điều khiển VF e34 thay theo chu kỳ nào?

**Đáp án golden:** Pin chìa khóa điều khiển VF e34 được thay mới mỗi 24 tháng hoặc sau 24.000 km.

**Câu trả lời thực:**

Đối với dòng xe VinFast VF e34, pin chìa khóa điều khiển cần được thay mới định kỳ cứ 24 tháng hoặc sau 24.000km, tùy theo điều kiện nào đến trước [Tài liệu 1].

**Lỗi:** None; confidence: high; fallback: False

**Nguồn được trả về:**

```json
[
  {
    "document_id": "lich_bao_duong_ALL",
    "title": "Lịch bảo dưỡng xe VinFast định kỳ dành cho ô tô, xe máy điện",
    "section": "1.6. Lịch bảo dưỡng xe VF e34",
    "source_url": "https://shop.vinfastauto.com/vn_vi/dat-lich-dich-vu.html",
    "chunk_id": "lich_bao_duong_ALL_chk_0023",
    "score": 0.9957
  }
]
```

## M03

**Câu hỏi:** Từ năm 2026, chu kỳ bảo dưỡng định kỳ của ô tô điện VinFast là bao lâu?

**Đáp án golden:** Từ 01/01/2026, VinFast điều chỉnh mốc bảo dưỡng định kỳ cho ô tô điện thành 15.000 km hoặc 1 năm, tùy điều kiện nào đến trước.

**Câu trả lời thực:**

Từ ngày 01/01/2026, VinFast chính thức điều chỉnh mốc bảo dưỡng định kỳ cho các dòng ô tô điện là **15.000 km hoặc 1 năm** (tùy theo điều kiện nào đến trước) [Tài liệu 1]. 

Mốc điều chỉnh này thay thế cho mốc cũ là 12.000 km hoặc 1 năm [Tài liệu 1]. Lưu ý rằng quy định này không áp dụng đối với phiên bản Lạc Hồng chống đạn [Tài liệu 1].

**Lỗi:** None; confidence: high; fallback: False

**Nguồn được trả về:**

```json
[
  {
    "document_id": "toi_uu_moc_bao_duong_ALL",
    "title": "VINFAST TỐI ƯU MỐC BẢO DƯỠNG, GIẢM CHI PHÍ VẬN HÀNH CHO KHÁCH HÀNG",
    "section": "VINFAST TỐI ƯU MỐC BẢO DƯỠNG, GIẢM CHI PHÍ VẬN HÀNH CHO KHÁCH HÀNG",
    "source_url": null,
    "chunk_id": "toi_uu_moc_bao_duong_ALL_chk_0001",
    "score": 0.9994
  }
]
```

## P01

**Câu hỏi:** Sạc tại nhà VinFast 3 kW có giá bao nhiêu?

**Đáp án golden:** Sạc tại nhà VinFast 3 kW có giá niêm yết 8.836.365 VNĐ trên VinFast eStore tại thời điểm đối chiếu.

**Câu trả lời thực:**

Hiện tài liệu chính hãng chưa có thông tin chi tiết về giá của bộ sạc tại nhà VinFast 3 kW. Tài liệu hiện có chỉ cung cấp đơn giá sạc tại trạm sạc công cộng là 3.858 VNĐ/kWh [Tài liệu 1]. Để biết thông tin chính xác về chi phí mua hoặc lắp đặt bộ sạc tại nhà, quý khách vui lòng liên hệ trực tiếp với xưởng dịch vụ hoặc đại lý ủy quyền của VinFast để được hỗ trợ.

**Lỗi:** None; confidence: low; fallback: True

**Nguồn được trả về:**

```json
[
  {
    "document_id": "pricing_tram_sac_ALL",
    "title": "Biểu phí trạm sạc và thiết bị sạc VinFast",
    "section": "Đơn giá sạc tại trạm sạc công cộng",
    "source_url": "https://vinfastauto.com/vn_vi/dich-vu-pin-oto-dien",
    "chunk_id": "pricing_tram_sac_ALL_chk_0002",
    "score": 0.9996
  }
]
```

## P11

**Câu hỏi:** Dịch vụ cứu hộ pin xe điện VinFast có mất tiền không?

**Đáp án golden:** Có. Dịch vụ cứu hộ pin VinFast có chi phí 50.000 VNĐ/lần, bao gồm việc kỹ thuật viên đến sạc pin tại chỗ trong 15 phút.

**Câu trả lời thực:**

Dịch vụ cứu hộ pin ô tô điện VinFast có tính phí với mức giá là 50.000 VNĐ cho mỗi lần thực hiện [Tài liệu 1].

**Lỗi:** None; confidence: high; fallback: False

**Nguồn được trả về:**

```json
[
  {
    "document_id": "battery_cuu_ho_ALL",
    "title": "Dịch vụ cứu hộ pin ô tô điện VinFast",
    "section": "Chi phí và thời gian sạc tại chỗ",
    "source_url": "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap",
    "chunk_id": "battery_cuu_ho_ALL_chk_0003",
    "score": 0.9995
  }
]
```
