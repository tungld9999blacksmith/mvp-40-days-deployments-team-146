import asyncio
import os
import sys
from pathlib import Path

# Fix Windows console encoding for UTF-8 Vietnamese diacritics
if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")

# Disable LangSmith tracing to prevent 403 network warnings
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# Add paths to sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
root_dir = backend_dir.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv

# Load the single .env at the repo root
env_path = backend_dir.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

from src.agents import graph as graph_module  # type: ignore
from src.agents.graph import route_intent  # type: ignore
from src.agents.state import AgentState  # type: ignore


def test_route_intent():
    # Test 1: General greeting -> respond
    state_general: AgentState = {"query": "Xin chào, bạn có khỏe không?"}
    assert route_intent(state_general) == "respond"

    # Test 2: RAG question -> rag_retrieval
    state_rag: AgentState = {"query": "Lịch bảo dưỡng xe VF 8 mốc 24000 km là gì?"}
    assert route_intent(state_rag) == "rag_retrieval"

    # Test 3: Warranty question -> rag_retrieval
    state_warranty: AgentState = {"query": "Chính sách bảo hành pin xe Klara"}
    assert route_intent(state_warranty) == "rag_retrieval"

    print("PASS: test_route_intent passed all checks!")


def test_agent_graph_execution():
    asyncio.run(_async_test_agent_graph_execution())


async def _async_test_agent_graph_execution():
    print("\n--- TEST: Running agent.ainvoke with RAG query ---")
    query = "Xe VF e34 đi 24000 km cần bảo dưỡng những hạng mục gì?"
    input_state: AgentState = {
        "query": query,
        "vehicle_model": "VFe34",
        "current_odometer_km": 24000,
    }

    result = await graph_module.agent.ainvoke(
        input_state,
        config={"configurable": {"thread_id": "test-agent-graph-001"}},
    )

    print(f"Query: {query}")
    print(f"Response:\n{result.get('response')}")
    print(f"\nConfidence: {result.get('confidence')}")
    print(f"Fallback required: {result.get('fallback_required')}")
    citations = result.get("citations", [])
    print(f"Citations count: {len(citations)}")
    for i, c in enumerate(citations):
        print(f"  [{i + 1}] {c.get('title')} | Section: {c.get('section')} | Doc: {c.get('document_id')}")

    assert result.get("response") is not None
    assert len(result.get("response")) > 0
    # Citations chỉ xuất hiện khi agent gọi RAG tool hoặc get_due_maintenance
    citations = result.get("citations", [])
    print(f"Citations count: {len(citations)}")
    print("\nPASS: test_agent_graph_execution succeeded perfectly!")


if __name__ == "__main__":
    test_route_intent()
    test_agent_graph_execution()
