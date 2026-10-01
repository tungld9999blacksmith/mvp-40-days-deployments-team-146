# Qdrant vector store

The application uses Qdrant for knowledge retrieval and optional chat semantic
search. PostgreSQL still stores users, bookings, conversations and messages.

Configure the root `.env` (never commit the API key):

```dotenv
VECTOR_STORE=qdrant
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION_NAME=ev_care_knowledge_base
EMBEDDING_PROVIDER=gemini
EMBEDDING_DIMENSIONS=3072
EMBEDDING_GEMINI_MODEL=gemini-embedding-001
```

The existing knowledge collection uses Gemini embeddings with 3072 dimensions
and cosine distance. Keep the embedding model and dimensions consistent with
ingestion. Changing the store does not automatically migrate or re-embed data.
The adapters reject incompatible collection dimensions without recreating the
collection. The chat retrieval adapter preserves document IDs and page numbers
from the RAG payloads for citations.

`QDRANT_COLLECTION_NAME` holds knowledge chunks. Optional chat embeddings use a
separate `conversation_messages` collection with a `metadata.conversationId`
filter. They remain disabled unless `CONVERSATION_SEMANTIC_INDEX_ENABLED=true`.

If `QDRANT_URL` is empty, Qdrant uses embedded local storage at
`./data/qdrant_local` relative to the backend's working directory. This mode is
for a single process; use Qdrant Cloud/server with API and Celery processes.

Docker Compose no longer starts Chroma. Restart the backend and workers after
changing `.env`; rebuild the backend image when using Docker. Existing Chroma
files and volumes are not deleted by this change.

The old `scripts/migrate_to_qdrant.py` is only for an explicit one-time import
from legacy Chroma data. It requires installing `chromadb` separately in a
migration environment; normal backend installation no longer includes it.

Run the offline adapter and health checks from `backend/`:

```sh
python -m pytest tests/test_infrastructure/test_qdrant_vectorstore.py -q
```

Qdrant API references: [query points](https://api.qdrant.tech/api-reference/search/query-points)
and [payload indexes](https://qdrant.tech/documentation/manage-data/indexing/).
