from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from ...config import get_settings

settings = get_settings()


class ChromaService:
    def __init__(
        self,
        host: str = settings.chroma_host,
        port: int = settings.chroma_port,
        user: str = settings.chroma_user,
        password: str = settings.chroma_password,
    ) -> None:
        chroma_settings = ChromaSettings()
        if user and password:
            chroma_settings = ChromaSettings(
                chroma_client_auth_provider="chromadb.auth.basic_authn.BasicAuthClientProvider",
                chroma_client_auth_credentials=f"{user}:{password}",
            )

        self._client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=chroma_settings,
        )

    def get_or_create_collection(self, name: str) -> Collection:
        return self._client.get_or_create_collection(name=name)

    def add(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        collection = self.get_or_create_collection(collection_name)
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def query(
        self,
        collection_name: str,
        query_texts: list[str],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        collection = self.get_or_create_collection(collection_name)
        return collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where=where,
        )

    def delete(
        self,
        collection_name: str,
        ids: list[str],
    ) -> None:
        collection = self.get_or_create_collection(collection_name)
        collection.delete(ids=ids)

    def delete_collection(self, collection_name: str) -> None:
        self._client.delete_collection(name=collection_name)

    def list_collections(self) -> list[str]:
        return [collection.name for collection in self._client.list_collections()]

    def heartbeat(self) -> int:
        return self._client.heartbeat()
