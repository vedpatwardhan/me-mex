export type NodeType =
  | 'paper'
  | 'blog'
  | 'video'
  | 'post'
  | 'concept';

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
  is_directional?: boolean;
  text_body?: string;
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

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  is_voice?: boolean;
  timestamp: string;
  grounded_node_ids?: string[];
  report?: {
    id: string;
    title: string;
    markdown_content: string;
  };
}

export interface AgentThinkingState {
  isThinking: boolean;
  currentAction: string;
  visitedNodeIds: string[];
}
