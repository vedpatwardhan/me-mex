export type NodeType =
  | 'ROOT'
  | 'CONCEPT'
  | 'paper'
  | 'blog'
  | 'video'
  | 'post'
  | 'concept';

export type NodeTypeFilter =
  | 'all'
  | 'paper'
  | 'blog'
  | 'post'
  | 'immutable_concept'
  | 'mutable_concept';

export interface GraphNode {
  id: string;
  node_type: NodeType;
  title: string;
  content: string;
  raw_doc_id?: string;
  is_immutable?: boolean;
  project_ids: string[];
  metadata: Record<string, any>;
  created_at: string;
  updated_at: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

export const isRootNode = (node: GraphNode): boolean => {
  const t = (node.node_type || '').toLowerCase();
  return (
    t === 'root' ||
    t === 'paper' ||
    t === 'blog' ||
    t === 'post' ||
    t === 'video' ||
    node.id.startsWith('root_')
  );
};

export const getRootSubType = (node: GraphNode): 'paper' | 'blog' | 'post' | 'root' => {
  const t = (node.node_type || '').toLowerCase();
  if (t === 'paper' || node.metadata?.doc_type === 'paper') return 'paper';
  if (t === 'blog' || node.metadata?.doc_type === 'blog') return 'blog';
  if (t === 'post' || node.metadata?.doc_type === 'post') return 'post';
  return 'root';
};

export const isConceptNode = (node: GraphNode): boolean => {
  return !isRootNode(node);
};

export const isImmutableConcept = (node: GraphNode): boolean => {
  if (isRootNode(node)) return true;
  return !!(
    node.metadata?.immutable === true ||
    node.is_immutable === true ||
    node.metadata?.root_node_id
  );
};


export interface GraphEdge {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  source_node_id?: string;
  target_node_id?: string;
  is_directional?: boolean;
  description?: string;
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

export interface IngestionProgressEvent {
  event: 'intent_classified' | 'passage_extraction_progress' | 'ingestion_completed' | 'chat_complete' | 'error';
  intent?: string;
  current_chunk?: number;
  total_chunks?: number;
  doc_title?: string;
  message?: string;
  reply?: string;
  grounded_node_ids?: string[];
}
