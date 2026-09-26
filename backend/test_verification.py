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
            f"  - Edge [{e.id}]: {e.source_id} --({dir_label})--> {e.target_id} | Context: '{e.text_body}'"
        )

    # Assert at least one undirected edge exists in seed data
    undirected_edges = [e for e in edges if not getattr(e, "is_directional", True)]
    assert (
        len(undirected_edges) > 0
    ), "Expected at least one undirected edge in seed data!"
    print(
        f"✓ Dual-Mode Edge Schema verified: {len(undirected_edges)} undirected symmetric edge(s) found."
    )

    # 2. Test Graph Analytics & Concept Hub Discovery
    print("\n--- Testing Graph Analytics (rustworkx Centrality & Concept Hubs) ---")
    centrality = graph_analytics.calculate_hub_centrality()
    print(f"✓ Calculated Centrality: {centrality}")
    top_hubs = graph_analytics.get_top_concept_hubs(top_k=4)
    print(f"✓ Discovered {len(top_hubs)} Dynamic Concept Hubs:")
    for hub_node, score in top_hubs:
        print(
            f"  - Concept Hub: '{hub_node.title}' (ID: {hub_node.id}, Score: {score})"
        )

    # 3. Test Intent Router & Direct Conversation Flow
    print("\n--- Testing Executive Orchestrator Intent Router ---")
    chat_intent = orchestrator.classify_intent("Hello, how are you?")
    print(f"✓ Classified 'Hello, how are you?' intent: {chat_intent}")
    assert chat_intent == "DIRECT_CONVERSATION"

    retrieval_intent = orchestrator.classify_intent(
        "Explain latent world models synthesis"
    )
    print(f"✓ Classified research prompt intent: {retrieval_intent}")
    assert retrieval_intent == "GRAPH_RETRIEVAL"

    ingest_intent = orchestrator.classify_intent(
        "https://arxiv.org/abs/2401.00001 paper abstract"
    )
    print(f"✓ Classified URL prompt intent: {ingest_intent}")
    assert ingest_intent == "DOCUMENT_INGESTION"

    print("\n--- Testing Unified Process User Message Stream ---")
    async for event in orchestrator.process_user_message("What can you help me with?"):
        evt_type = event.get("event")
        if evt_type == "intent_classified":
            print(f"  [SSE Event] Intent: {event['intent']}")
        elif evt_type == "chat_complete":
            print(f"  [SSE Event] Direct Response: {event['final_answer'][:100]}...")

    # 4. Test Retrieval Stream (User Flow 2)
    print("\n--- Testing Multi-Persona Retrieval Flow (User Flow 2) ---")
    async for event in orchestrator.execute_retrieval_flow(
        "latent world models planning"
    ):
        evt_type = event.get("event")
        if evt_type == "persona_traversal_active":
            dept = event.get("department_name")
            dept_id = event.get("department_id")
            traversed = event.get("traversing_node_ids")
            print(f"  [SSE Event] {dept} ({dept_id}) traversing nodes -> {traversed}")
        elif evt_type == "chat_complete":
            print(
                f"  [SSE Event] Chat Complete!\nSynthesis: {event['final_answer'][:120]}..."
            )

    # 5. Test Ingestion Stream (User Flow 1)
    print("\n--- Testing Document Ingestion & Delta Patch Flow (User Flow 1) ---")
    title = "LeWM: Latent Efficient World Models for MPC"
    text = "LeWM introduces a joint-embedding predictive architecture for 100x faster trajectory rollouts in latent state representation."
    async for event in orchestrator.execute_ingestion_flow(title, text):
        evt_type = event.get("event")
        if evt_type == "orchestrator_tool_call":
            print(f"  [SSE Event] Tool Call: {event['tool_name']} ({event['args']})")
        elif evt_type == "node_touched":
            print(
                f"  [SSE Event] Node Touched: '{event['node_title']}' by {event['persona_name']}"
            )
        elif evt_type == "tool_complete":
            print(
                f"  [SSE Event] Tool Complete! Concept ID: {event['concept_id']}, Passages: {event['passage_pointers']}"
            )

    # 6. Test Project Workspaces & Scoped project_ids Filtering
    print("\n--- Testing Project Workspaces & Scoped Filtering ---")
    from app.models import ProjectWorkspace, GraphNode

    # Test Project Workspace creation
    new_proj = ProjectWorkspace(
        _id="proj_vla_research",
        name="VLA Policies & Steering",
        description="Focused workspace for Vision-Language-Action models.",
    )
    db_engine.upsert_project(new_proj)
    projs = db_engine.get_projects()
    print(f"✓ Total projects in DB: {len(projs)}")
    assert any(
        p.id == "proj_vla_research" for p in projs
    ), "New project workspace not found!"

    # Create a node scoped specifically to proj_vla_research
    scoped_node = GraphNode(
        _id="concept_vla_flow",
        title="VLA Action Flow Steering",
        text_body="Diffusion action trajectory flow matching.",
        project_ids=["global", "proj_vla_research"],
    )
    db_engine.upsert_node(scoped_node)

    # Test Scoped vs Global Graph Filtering
    global_nodes = db_engine.get_nodes("global")
    vla_nodes = db_engine.get_nodes("proj_vla_research")
    other_nodes = db_engine.get_nodes("proj_unrelated")

    print(f"✓ Global graph node count: {len(global_nodes)}")
    print(f"✓ VLA Project graph node count: {len(vla_nodes)}")
    print(f"✓ Unrelated Project graph node count: {len(other_nodes)}")

    assert any(
        n.id == "concept_vla_flow" for n in global_nodes
    ), "Node should exist in global master superset graph!"
    assert any(
        n.id == "concept_vla_flow" for n in vla_nodes
    ), "Node should exist in vla_research scoped graph!"
    assert not any(
        n.id == "concept_vla_flow" for n in other_nodes
    ), "Node should NOT exist in unrelated project graph!"
    print(
        "✓ Project Workspace bidirectional referencing & scoped graph isolation verified successfully."
    )

    print("\n=== ALL GRAPH-MEMEX BACKEND CHECKS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    asyncio.run(test_backend_verification())
