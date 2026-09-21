export type NodeType =
  | 'external_source'
  | 'human_insight'
  | 'agent_hypothesis'
  | 'concept_phrase'
  | 'falsified_path';

export type EdgeType =
  | 'BUILDS_UPON'
  | 'CONTRASTS_WITH'
  | 'REFUTES'
  | 'DERIVES_FROM'
  | 'CATEGORY_MEMBER';

export interface GraphNode {
  id: string;
  node_type: NodeType;
  title: string;
  takeaway_2line: string;
  content: string;
  raw_doc_id?: string;
  project_ids: string[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  // Canvas force simulation properties
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  source_node_id?: string;
  target_node_id?: string;
  edge_type: EdgeType;
  weight: number;
  provenance_quote?: string;
  project_ids: string[];
  created_at: string;
}

export interface ProjectWorkspace {
  id: string;
  name: string;
  description: string;
  node_ids: string[];
  edge_ids: string[];
  created_at: string;
}

export interface AgentProposal {
  id: string;
  proposal_type: 'link' | 'node' | 'hypothesis' | 'merge';
  title: string;
  description: string;
  source_node_id?: string;
  target_node_id?: string;
  suggested_edge_type?: EdgeType;
  status: 'pending' | 'accepted' | 'rejected';
  created_at: string;
}

export interface ReportResponse {
  id: string;
  title: string;
  markdown_content: string;
  provenance_mappings: Record<string, string>;
  created_at: string;
}
