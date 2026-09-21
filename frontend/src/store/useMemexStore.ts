import { create } from 'zustand';
import { AgentProposal, GraphEdge, GraphNode, NodeType, ProjectWorkspace, ReportResponse } from '../types';

interface MemexState {
  viewMode: 'global' | 'workspace' | 'report' | 'intake';
  activeProjectId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  projects: ProjectWorkspace[];
  proposals: AgentProposal[];
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  traversingNodeIds: string[];
  searchQuery: string;
  selectedNodeTypeFilter: NodeType | 'all';
  isVoiceListening: boolean;
  voiceTranscript: string;
  voiceResponse: string | null;
  currentReport: ReportResponse | null;
  isLoading: boolean;

  // Actions
  setViewMode: (mode: 'global' | 'workspace' | 'report' | 'intake') => void;
  setActiveProjectId: (projectId: string) => void;
  setSelectedNodeId: (id: string | null) => void;
  setHoveredNodeId: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setSelectedNodeTypeFilter: (filter: NodeType | 'all') => void;
  setVoiceListening: (listening: boolean) => void;
  setVoiceTranscript: (transcript: string) => void;

  // API Async Actions
  fetchGraphData: () => Promise<void>;
  fetchProjects: () => Promise<void>;
  fetchProposals: () => Promise<void>;
  handleIntake: (sourceType: 'url' | 'voice' | 'text' | 'pdf', contentOrUrl: string, titleHint?: string) => Promise<void>;
  handleProposalAction: (proposalId: string, action: 'accept' | 'reject') => Promise<void>;
  generateReport: (title: string, targetNodeIds: string[]) => Promise<void>;
  createNode: (node: Partial<GraphNode>) => Promise<void>;
  createEdge: (sourceId: string, targetId: string, edgeType: string) => Promise<void>;
  simulateVoiceCommand: (speechText: string) => Promise<void>;
}

export const useMemexStore = create<MemexState>((set, get) => ({
  viewMode: 'global',
  activeProjectId: 'global',
  nodes: [],
  edges: [],
  projects: [],
  proposals: [],
  selectedNodeId: 'node_1',
  hoveredNodeId: null,
  traversingNodeIds: [],
  searchQuery: '',
  selectedNodeTypeFilter: 'all',
  isVoiceListening: false,
  voiceTranscript: '',
  voiceResponse: null,
  currentReport: null,
  isLoading: false,

  setViewMode: (viewMode) => set({ viewMode }),
  setActiveProjectId: async (activeProjectId) => {
    set({ activeProjectId });
    await get().fetchGraphData();
  },
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
  setHoveredNodeId: (hoveredNodeId) => set({ hoveredNodeId }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSelectedNodeTypeFilter: (selectedNodeTypeFilter) => set({ selectedNodeTypeFilter }),
  setVoiceListening: (isVoiceListening) => set({ isVoiceListening }),
  setVoiceTranscript: (voiceTranscript) => set({ voiceTranscript }),

  fetchGraphData: async () => {
    set({ isLoading: true });
    try {
      const res = await fetch(`/api/graph?project_id=${get().activeProjectId}`);
      const data = await res.json();
      set({ nodes: data.nodes || [], edges: data.edges || [] });
    } catch (err) {
      console.error('Failed to fetch graph:', err);
    } finally {
      set({ isLoading: false });
    }
  },

  fetchProjects: async () => {
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();
      set({ projects: data || [] });
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    }
  },

  fetchProposals: async () => {
    try {
      const res = await fetch('/api/proposals');
      const data = await res.json();
      set({ proposals: data || [] });
    } catch (err) {
      console.error('Failed to fetch proposals:', err);
    }
  },

  handleIntake: async (sourceType, contentOrUrl, titleHint) => {
    set({ isLoading: true });
    try {
      const res = await fetch('/api/intake', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_type: sourceType,
          content_or_url: contentOrUrl,
          title_hint: titleHint,
          project_id: get().activeProjectId
        })
      });
      const data = await res.json();
      if (data.seed_traversal) {
        set({ traversingNodeIds: data.seed_traversal });
        setTimeout(() => set({ traversingNodeIds: [] }), 3500);
      }
      await get().fetchGraphData();
      if (data.node) {
        set({ selectedNodeId: data.node.id });
      }
    } catch (err) {
      console.error('Intake failed:', err);
    } finally {
      set({ isLoading: false });
    }
  },

  handleProposalAction: async (proposalId, action) => {
    try {
      await fetch(`/api/proposals/${proposalId}/action?action=${action}`, { method: 'POST' });
      await get().fetchProposals();
      await get().fetchGraphData();
    } catch (err) {
      console.error('Proposal action failed:', err);
    }
  },

  generateReport: async (title, targetNodeIds) => {
    set({ isLoading: true, viewMode: 'report' });
    try {
      const res = await fetch('/api/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          target_node_ids: targetNodeIds,
          project_id: get().activeProjectId
        })
      });
      const report = await res.json();
      set({ currentReport: report });
    } catch (err) {
      console.error('Report generation failed:', err);
    } finally {
      set({ isLoading: false });
    }
  },

  createNode: async (nodeData) => {
    const newId = `node_${Date.now()}`;
    const newNode: GraphNode = {
      id: newId,
      node_type: nodeData.node_type || 'human_insight',
      title: nodeData.title || 'New Node',
      takeaway_2line: nodeData.takeaway_2line || 'User entered insight node.',
      content: nodeData.content || '',
      project_ids: ['global', get().activeProjectId],
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newNode)
    });
    await get().fetchGraphData();
    set({ selectedNodeId: newId });
  },

  createEdge: async (sourceId, targetId, edgeType) => {
    const newEdge: GraphEdge = {
      id: `edge_${Date.now()}`,
      source: sourceId,
      target: targetId,
      source_node_id: sourceId,
      target_node_id: targetId,
      edge_type: edgeType as any || 'BUILDS_UPON',
      weight: 1.0,
      project_ids: ['global', get().activeProjectId],
      created_at: new Date().toISOString()
    };
    await fetch('/api/edges', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newEdge)
    });
    await get().fetchGraphData();
  },

  simulateVoiceCommand: async (speechText) => {
    set({ isVoiceListening: true, voiceTranscript: speechText, voiceResponse: 'Processing spoken insight & querying memory graph...' });
    
    setTimeout(async () => {
      // Intelligently check command type
      const lower = speechText.toLowerCase();
      if (lower.includes('report')) {
        await get().generateReport('Voice Requested Synthesis', get().nodes.map(n => n.id));
        set({ voiceResponse: 'Generated report based on current graph selection!' });
      } else if (lower.includes('add') || lower.includes('insight') || lower.includes('thought')) {
        await get().handleIntake('voice', speechText, 'Voice Epiphany');
        set({ voiceResponse: 'Spoken insight parsed, bi-directionally ingested, and linked to Global Graph!' });
      } else if (lower.includes('search') || lower.includes('show') || lower.includes('find')) {
        const matched = get().nodes.find(n => lower.includes(n.title.toLowerCase().slice(0, 5)));
        if (matched) {
          set({ selectedNodeId: matched.id, traversingNodeIds: [matched.id] });
          set({ voiceResponse: `Located node: "${matched.title}". Panned visual canvas to subgraph.` });
        } else {
          set({ voiceResponse: 'Traversed graph subgraphs for relevant nodes.' });
        }
      } else {
        set({ voiceResponse: `Grounded Agent: "Analyzed '${speechText}'. Highlighted active nodes on canvas."` });
      }
      set({ isVoiceListening: false });
    }, 1500);
  }
}));
