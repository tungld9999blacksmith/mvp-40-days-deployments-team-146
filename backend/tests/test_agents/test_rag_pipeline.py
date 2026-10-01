from pathlib import Path

from src.agents.tools.RAG.ingestion import (
    DocumentChunker,
    DocumentMetadata,
    IngestionEngine,
    RawDocument,
    TextCleaner,
)
from src.agents.tools.RAG.query import (
    RAGPipeline,
    get_maintenance_schedule_rag,
    get_warranty_policy_rag,
    search_ev_knowledge,
)


def test_text_cleaner_normalizes_unicode_and_tables():
    cleaner = TextCleaner()
    raw = RawDocument(
        doc_id="test_doc",
        content="""
        # Tiêu đề &amp; Giới thiệu&nbsp;
        Trang 1 / 10

        | Dòng xe | Mốc km | Chi phí |
        |---|---|---|
        | VF 6 | 20.000 | 700.000 |
        """,
        metadata=DocumentMetadata(
            source="test.html",
            doc_id="test_doc",
            title="Tiêu đề & Giới thiệu",
            file_type="html",
            model="VF6",
            category="pricing",
        ),
    )

    cleaned = cleaner.clean(raw)
    assert "&amp;" not in cleaned.cleaned_content
    assert "&nbsp;" not in cleaned.cleaned_content
    assert "Trang 1 / 10" not in cleaned.cleaned_content
    assert "VF 6" in cleaned.cleaned_content
    assert cleaned.char_count > 0


def test_chunker_splits_by_headers():
    chunker = DocumentChunker(chunk_size=300, chunk_overlap=50)
    cleaner = TextCleaner()
    raw = RawDocument(
        doc_id="test_schedule",
        content="""
        # Lịch bảo dưỡng xe điện
        ## Mốc 10000 km
        Kiểm tra hệ thống phanh và dung dịch làm mát.
        ## Mốc 20000 km
        Thay lọc gió điều hòa và kiểm tra ắc quy 12V.
        """,
        metadata=DocumentMetadata(
            source="schedule.html",
            doc_id="test_schedule",
            title="Lịch bảo dưỡng",
            file_type="html",
            model="VF5",
            category="maintenance",
        ),
    )
    cleaned = cleaner.clean(raw)
    chunks = chunker.chunk_document(cleaned)

    assert len(chunks) >= 2
    assert any("Mốc 10000 km" in c.content for c in chunks)
    assert any("Mốc 20000 km" in c.content for c in chunks)
    assert all(c.metadata["category"] == "maintenance" for c in chunks)


def test_ingestion_engine_html(tmp_path: Path):
    engine = IngestionEngine()
    html_file = tmp_path / "test_warranty.html"
    html_file.write_text(
        "<html><head><title>Chính sách bảo hành Pin</title></head><body><h1>Bảo hành pin</h1><p>Bảo hành 8 năm.</p></body></html>",
        encoding="utf-8",
    )

    doc = engine.ingest_file(html_file)
    assert doc.doc_id == "test_warranty"
    assert "Bảo hành pin" in doc.content
    assert doc.metadata.category == "warranty"


def test_vector_store_and_pipeline_end_to_end(tmp_path: Path):
    # Setup temporary directory for pipeline
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    # Create dummy raw file
    dummy_doc = raw_dir / "cam_nang_bao_duong.html"
    dummy_doc.write_text(
        """<html>
        <head><title>Cẩm nang bảo dưỡng định kỳ VF6</title></head>
        <body>
        <h1>Cẩm nang bảo dưỡng định kỳ xe điện</h1>
        <h2>Mốc 20.000 km</h2>
        <p>Thay lọc gió cabin than hoạt tính và kiểm tra điện áp bình 12V.</p>
        </body>
        </html>""",
        encoding="utf-8",
    )

    engine = IngestionEngine()
    docs = engine.ingest_directory(raw_dir)
    assert len(docs) == 1


def test_rag_tools_invoke():
    # Test tools invoke with existing indexed knowledge
    res_warranty = get_warranty_policy_rag.invoke({"model": "VF8", "component": "pin"})
    assert "bảo hành" in res_warranty.lower()
    assert "vinfast" in res_warranty.lower() or "vf8" in res_warranty.lower()

    res_maintenance = get_maintenance_schedule_rag.invoke({"model": "VF6", "km": 20000})
    assert "bảo dưỡng" in res_maintenance.lower()

    res_pricing = search_ev_knowledge.invoke({"query": "giá lọc gió điều hòa than hoạt tính", "category": "pricing"})
    assert len(res_pricing) > 0
