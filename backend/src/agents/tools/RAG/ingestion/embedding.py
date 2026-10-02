from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

from .config import rag_settings

load_dotenv()

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Giao diện chuẩn hóa cho các model embedding kết nối Qdrant."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Sinh vector embedding cho danh sách tài liệu/chunk."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Sinh vector embedding cho câu truy vấn tìm kiếm."""
        pass


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding sử dụng Google Gemini API (models/gemini-embedding-001, vector 3072 chiều)."""

    def __init__(self, api_key: str | None = None, model: str = "models/gemini-embedding-001") -> None:
        from google import genai

        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        self.model = model

        if not self.api_key or self.api_key.startswith("your_"):
            raise ValueError("GOOGLE_API_KEY hoặc GEMINI_API_KEY chưa được cấu hình.")

        self._client = genai.Client(api_key=self.api_key)
        logger.info(f"Khởi tạo GeminiEmbeddingProvider với model: {self.model} (3072 dims)")

    def embed_documents(self, texts: list[str], batch_size: int = 32, max_retries: int = 5) -> list[list[float]]:
        import time

        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            success = False
            last_err = None

            for attempt in range(max_retries):
                try:
                    response = self._client.models.embed_content(
                        model=self.model,
                        contents=batch,
                    )
                    if response.embeddings:
                        for item in response.embeddings:
                            if item.values:
                                all_embeddings.append(list(item.values))
                    success = True
                    break
                except Exception as e:
                    last_err = e
                    err_msg = str(e)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        wait_seconds = 10 * (attempt + 1)
                        logger.warning(
                            f"Gemini API 429 Rate Limit. Tự động chờ {wait_seconds}s trước khi thử lại (lần {attempt + 1}/{max_retries})..."
                        )
                        time.sleep(wait_seconds)
                    else:
                        raise e

            if not success:
                raise last_err or RuntimeError("Không thể lấy embedding sau nhiều lần thử lại.")

        return all_embeddings

    def embed_query(self, text: str, max_retries: int = 3) -> list[float]:
        import time

        for attempt in range(max_retries):
            try:
                response = self._client.models.embed_content(
                    model=self.model,
                    contents=[text],
                )
                if response.embeddings and response.embeddings[0].values:
                    return list(response.embeddings[0].values)
            except Exception as e:
                if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))
                else:
                    raise e
        return []


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding sử dụng OpenAI API (text-embedding-3-small hoặc text-embedding-ada-002)."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from langchain_openai import OpenAIEmbeddings
        from pydantic import SecretStr

        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or rag_settings.openai_embedding_model

        if not self.api_key or self.api_key.startswith("sk-your"):
            raise ValueError("OPENAI_API_KEY chưa được cấu hình hoặc là placeholder.")

        self._embeddings = OpenAIEmbeddings(
            api_key=SecretStr(self.api_key),
            model=self.model,
        )
        logger.info(f"Khởi tạo OpenAIEmbeddingProvider với model: {self.model}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)


def get_embedding_provider(preference: str = "auto") -> BaseEmbeddingProvider:
    """Tự động lựa chọn provider phù hợp cho Qdrant:
    1. Ưu tiên Gemini nếu có GOOGLE_API_KEY / GEMINI_API_KEY (3072 dims)
    2. Kế tiếp là OpenAI nếu có OPENAI_API_KEY (1536 dims)
    """
    google_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    has_valid_google = bool(google_key and not google_key.startswith("your_"))

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    has_valid_openai = bool(openai_key and not openai_key.startswith("sk-your"))

    if preference == "gemini" or (preference == "auto" and has_valid_google):
        try:
            return GeminiEmbeddingProvider(api_key=google_key)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo GeminiEmbeddingProvider: {e}. Thử provider khác...")

    if preference == "openai" or (preference == "auto" and has_valid_openai):
        try:
            return OpenAIEmbeddingProvider(api_key=openai_key)
        except Exception as e:
            logger.warning(f"Không thể khởi tạo OpenAIEmbeddingProvider: {e}.")

    # Mặc định vẫn cố khởi tạo Gemini
    return GeminiEmbeddingProvider()
