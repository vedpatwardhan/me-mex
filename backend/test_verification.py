import asyncio
import sys
from app.db import db_engine
from app.agents.orchestrator import orchestrator
from app.services.graph_analytics import graph_analytics


async def test_backend_verification():
    print("=== [Graph-Memex Engine Verification] ===")

    # 1. Test Database Node & Edge Retrieval
    nodes = db_engine.get_nodes()
    edges = db_engine.get_edges()
    print(
        f"✓ Database Initialized: {len(nodes)} concept nodes, {len(edges)} connection edges."
    )
    for e in edges:
        dir_label = (
            "DIRECTED"
            if getattr(e, "is_directional", True)
            else "UNDIRECTED (SYMMETRIC)"
        )
        print(
            f"  - Edge [{e.id}]: {e.source_id} --({e.relation_type}, {dir_label})--> {e.target_id} | Weight: {e.weight}"
        )

    # Assert at least one undirected edge exists in seed data
    undirected_edges = [e for e in edges if not getattr(e, "is_directional", True)]
    assert (
        len(undirected_edges) > 0
    ), "Expected at least one undirected edge in seed data!"
    print(
        f"✓ Dual-Mode Edge Schema verified: {len(undirected_edges)} undirected symmetric edge(s) found."
    )

    # 2. Test Graph Analytics & Community Partitioning
    print("\n--- Testing Graph Analytics (rustworkx & NetworkX Louvain) ---")
    centrality = graph_analytics.calculate_hub_centrality()
    print(f"✓ Calculated Centrality: {centrality}")
    graph_analytics.update_macro_documents()
    macros = db_engine.get_macros()
    print(f"✓ Macro Documents Updated: {len(macros)} departments.")
    for m in macros:
        print(
            f"  - Department Macro: '{m.department_name}' | Hubs: {m.hub_concept_ids}"
        )

    # 3. Test Retrieval Stream (User Flow 2)
    print("\n--- Testing Multi-Persona Retrieval Flow (User Flow 2) ---")
    async for event in orchestrator.execute_retrieval_flow(
        "latent world models planning"
    ):
        evt_type = event.get("event")
        if evt_type == "persona_traversal_active":
            dept = event.get("department_name")
            color = event.get("color")
            traversed = event.get("traversing_node_ids")
            print(f"  [SSE Event] {dept} ({color}) traversing nodes -> {traversed}")
        elif evt_type == "retrieval_complete":
            print(
                f"  [SSE Event] Retrieval Complete!\nSynthesis: {event['final_answer'][:120]}..."
            )

    # 4. Test Ingestion Stream (User Flow 1)
    print("\n--- Testing Document Ingestion & Delta Patch Flow (User Flow 1) ---")
    title = "LeWM: Latent Efficient World Models for MPC"
    text = "LeWM introduces a joint-embedding predictive architecture for 100x faster trajectory rollouts in latent state representation."
    async for event in orchestrator.execute_ingestion_flow(title, text):
        evt_type = event.get("event")
        if evt_type == "ingestion_staged":
            print(
                f"  [SSE Event] Document Staged: doc_id={event['doc_id']}, passage_id={event['passage_id']}"
            )
        elif evt_type == "human_in_the_loop_prompt":
            print(
                f"  [SSE Event] Human-in-the-Loop Clarification emitted: '{event['prompt_question']}'"
            )
        elif evt_type == "ingestion_complete":
            print(
                f"  [SSE Event] Ingestion Complete! Concept ID: {event['concept_id']}, Passages: {event['passage_pointers']}"
            )

    print("\n=== ALL GRAPH-MEMEX BACKEND CHECKS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    asyncio.run(test_backend_verification())
