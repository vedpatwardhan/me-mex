import json
import os
from typing import Dict, List, Optional
from models import (
    GraphEdge,
    GraphNode,
    ProjectWorkspace,
    RawDocument,
    AgentProposal,
    ReportResponse,
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "initial_data.json")


class MemexDatabase:
    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}
        self.raw_docs: Dict[str, RawDocument] = {}
        self.projects: Dict[str, ProjectWorkspace] = {}
        self.proposals: Dict[str, AgentProposal] = {}
        self.reports: Dict[str, ReportResponse] = {}
        self.load_defaults()

    def load_defaults(self):
        # 1. Projects
        self.projects["global"] = ProjectWorkspace(
            id="global",
            name="Global Master Graph",
            description="Master superset database across all paradigms and literature.",
            node_ids=[],
            edge_ids=[],
        )
        self.projects["proj_vla"] = ProjectWorkspace(
            id="proj_vla",
            name="Project: VLA Policies & Flow Steering",
            description="Focused research workspace on Vision-Language-Action policies and Latent Flow Matching.",
            node_ids=["node_1", "node_2", "node_5", "node_6", "node_8"],
            edge_ids=["edge_1", "edge_4", "edge_5"],
        )
        self.projects["proj_skeletal"] = ProjectWorkspace(
            id="proj_skeletal",
            name="Project: Skeletal Priors & Kinematics",
            description="Focused workspace on biomechanical alignment and skeletal prior MPC.",
            node_ids=["node_3", "node_4", "node_7", "node_9"],
            edge_ids=["edge_2", "edge_3"],
        )

        # 2. Graph Nodes
        initial_nodes = [
            GraphNode(
                id="node_1",
                node_type="paper",
                title="Google AI Co-Scientist Paper (2026)",
                takeaway_2line="Automated hypothesis evolution system scaling test-time compute through pairwise Elo tournaments and adversarial falsification.",
                content="# Towards an AI Co-Scientist\n\nGoogle DeepMind / Google Cloud AI.\n\nKey Mechanisms:\n- Iterative Assumption Identification\n- Pairwise Elo Tournaments\n- Falsification Reflection Agent\n- Meta-Review Compaction",
                project_ids=["global", "proj_vla"],
                metadata={
                    "url": "https://arxiv.org/abs/2601.00001",
                    "authors": ["DeepMind Team"],
                    "published": "2026-01-15",
                },
            ),
            GraphNode(
                id="node_2",
                node_type="paper",
                title="HippoRAG 2: Dual-Node Associative Recall",
                takeaway_2line="Decouples passage chunks from phrase nodes, running Personalized PageRank over memory for multi-hop retrieval.",
                content="# HippoRAG 2: Memory Graph Traversal\n\nSeparates raw text passages from conceptual phrase nodes to enable mathematical probability propagation across subgraphs without blowing up context windows.",
                project_ids=["global", "proj_vla"],
                metadata={
                    "url": "https://arxiv.org/abs/2410.00000",
                    "authors": ["Stanford NLP"],
                    "published": "2024-10-10",
                },
            ),
            GraphNode(
                id="node_3",
                node_type="paper",
                title="PhysCtrl: Physics-Based Humanoid Control",
                takeaway_2line="Integrates skeletal joint priors into model predictive control for dynamic contact stabilization.",
                content="# PhysCtrl Skeletal Priors\n\nDemonstrates that enforcing biomechanical joint limits reduces MPC trajectory search space by 40%.",
                project_ids=["global", "proj_skeletal"],
                metadata={
                    "url": "https://arxiv.org/abs/2605.11000",
                    "authors": ["Robotics Lab"],
                    "published": "2026-05-11",
                },
            ),
            GraphNode(
                id="node_4",
                node_type="post",
                title="Voice Note: Joint Limit Loss Injection",
                takeaway_2line="Personal voice epiphany on injecting skeletal kinematic loss directly into latent flow steering vectors.",
                content="## Voice Transcript (Recorded May 12, 2026)\n\n'Instead of running heavy IK solvers server-side during MPC execution, what if we condition the action denoiser directly on joint velocity constraints?'",
                project_ids=["global", "proj_skeletal"],
                metadata={
                    "recorded_via": "Voice Intake Stream",
                    "temporal_timestamp": "2026-05-12T14:30:00Z",
                },
            ),
            GraphNode(
                id="node_5",
                node_type="concept",
                title="Hypothesis #4: Flow Matching Action Denoiser + PPR Steering",
                takeaway_2line="Combines HippoRAG 2 Personalized PageRank topological paths with Flow Matching parameter space steering.",
                content="## Co-Scientist Synthesized Hypothesis #4\n\nBy propagating PageRank probabilities across the passage-phrase memory graph, we can dynamically steer the latent velocity field during action denoising.",
                project_ids=["global", "proj_vla"],
                metadata={"elo_score": 1345.5, "parent_ids": ["node_1", "node_2"]},
            ),
            GraphNode(
                id="node_6",
                node_type="concept",
                title="Concept: Personalized PageRank (PPR)",
                takeaway_2line="Graph traversal algorithm propagating random walk probability distribution from seed nodes.",
                content="Math formulation: $p^{(t+1)} = (1-\\alpha) M p^{(t)} + \\alpha v_{seed}$",
                project_ids=["global", "proj_vla"],
                metadata={"category": "Graph Algorithms"},
            ),
            GraphNode(
                id="node_7",
                node_type="concept",
                title="Falsified: Naive Global Latent Search Without Constraints",
                takeaway_2line="Direct unconstrained gradient descent on latent space collapsed trajectory stability under dynamic impacts.",
                content="~~Falsified Path~~\n\nRefuted by Reflection Agent in Cycle 1 due to divergence during contact phase transitions.",
                project_ids=["global", "proj_skeletal"],
                metadata={
                    "refuted_in_cycle": 1,
                    "falsification_reason": "Contact Phase Instability",
                },
            ),
            GraphNode(
                id="node_8",
                node_type="paper",
                title="PaperQA2 Reranking Contextual Summarization",
                takeaway_2line="Strips 90% of token noise by evaluating candidate chunks in micro-summarization passes.",
                content="# PaperQA2 Context Reduction\n\nPrevents lost-in-the-middle context window degradation by extracting atomic evidence snippets.",
                project_ids=["global", "proj_vla"],
                metadata={
                    "url": "https://arxiv.org/abs/2409.00000",
                    "authors": ["FutureHouse Team"],
                    "published": "2024-09-01",
                },
            ),
            GraphNode(
                id="node_9",
                node_type="post",
                title="Voice Note: SPA Canvas Physics Preference",
                takeaway_2line="User design rule: Decouple strong mesh links from weak category splines on react-force-graph.",
                content="## Voice Transcript (Recorded Sep 21, 2026)\n\n'Ensure the canvas visually distinguishes hard mechanistic dependencies from soft thematic memberships so the graph doesn't look like a hairball.'",
                project_ids=["global", "proj_skeletal"],
                metadata={
                    "recorded_via": "Voice Intake Stream",
                    "temporal_timestamp": "2026-09-21T10:00:00Z",
                },
            ),
        ]
        for n in initial_nodes:
            self.nodes[n.id] = n

        # 3. Graph Edges
        initial_edges = [
            GraphEdge(
                id="edge_1",
                source_node_id="node_5",
                target_node_id="node_1",
                is_directional=True,
                text_body="Derived from Co-Scientist tournament paradigm",
                weight=1.0,
                provenance_quote="Derived from Co-Scientist tournament paradigm",
                project_ids=["global", "proj_vla"],
            ),
            GraphEdge(
                id="edge_2",
                source_node_id="node_4",
                target_node_id="node_3",
                is_directional=False,
                text_body="Proposed joint velocity constraint vs PhysCtrl IK solver",
                weight=0.8,
                provenance_quote="Proposed joint velocity constraint vs PhysCtrl IK solver",
                project_ids=["global", "proj_skeletal"],
            ),
            GraphEdge(
                id="edge_3",
                source_node_id="node_7",
                target_node_id="node_3",
                is_directional=True,
                text_body="Failed unconstrained baseline",
                weight=1.0,
                provenance_quote="Failed unconstrained baseline",
                project_ids=["global", "proj_skeletal"],
            ),
            GraphEdge(
                id="edge_4",
                source_node_id="node_2",
                target_node_id="node_6",
                is_directional=True,
                text_body="Uses PPR for multi-hop recall",
                weight=1.0,
                provenance_quote="Uses PPR for multi-hop recall",
                project_ids=["global", "proj_vla"],
            ),
            GraphEdge(
                id="edge_5",
                source_node_id="node_5",
                target_node_id="node_2",
                is_directional=True,
                text_body="Incorporates dual-node graph memory",
                weight=0.9,
                provenance_quote="Incorporates dual-node graph memory",
                project_ids=["global", "proj_vla"],
            ),
            GraphEdge(
                id="edge_6",
                source_node_id="node_8",
                target_node_id="node_1",
                is_directional=False,
                text_body="Context reduction for literature agents",
                weight=0.7,
                provenance_quote="Context reduction for literature agents",
                project_ids=["global"],
            ),
        ]
        for e in initial_edges:
            self.edges[e.id] = e

        # 4. Agent Proposals
        initial_proposals = [
            AgentProposal(
                id="prop_1",
                proposal_type="link",
                title="Connect Voice Note #4 to Co-Scientist Hypothesis #4",
                description="Reflection agent detected structural alignment between your joint limit loss idea and Hypothesis #4.",
                source_node_id="node_4",
                target_node_id="node_5",
                suggested_edge_type="BUILDS_UPON",
                status="pending",
            ),
            AgentProposal(
                id="prop_2",
                proposal_type="hypothesis",
                title="Proposed Hypothesis #5: Bi-Temporal Graphiti Invalidation + FSRS",
                description="Generated by Co-Scientist Evolution agent in Cycle 3.",
                status="pending",
            ),
        ]
        for p in initial_proposals:
            self.proposals[p.id] = p


db = MemexDatabase()
