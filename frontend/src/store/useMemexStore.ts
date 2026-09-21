import { create } from 'zustand';
import { AgentThinkingState, ChatMessage, GraphEdge, GraphNode, NodeType, ProjectWorkspace } from '../types';

interface MemexState {
  activeProjectId: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  projects: ProjectWorkspace[];
  chatHistory: Record<string, ChatMessage[]>;
  thinkingState: AgentThinkingState;
  selectedNodeId: string | null;
  hoveredNodeId: string | null;
  searchQuery: string;
  selectedNodeTypeFilter: NodeType | 'all';
  isVoiceListening: boolean;
  isLoading: boolean;

  // Actions
  setActiveProjectId: (projectId: string) => Promise<void>;
  setSelectedNodeId: (id: string | null) => void;
  setHoveredNodeId: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setSelectedNodeTypeFilter: (filter: NodeType | 'all') => void;
  setVoiceListening: (listening: boolean) => void;

  // API Async Actions
  fetchGraphData: () => Promise<void>;
  fetchProjects: () => Promise<void>;
  sendMessage: (text: string, isVoice?: boolean) => Promise<void>;
  createProjectWorkspace: (name: string, description: string) => Promise<void>;
  createEdge: (sourceId: string, targetId: string, edgeType: string) => Promise<void>;
}

const initialDefaultChat: Record<string, ChatMessage[]> = {
  global: [
    {
      id: 'msg_1',
      sender: 'agent',
      text: 'Welcome to Graph-Memex Master Superset. State an insight, paste arXiv URLs/DOIs, or ask for cross-paradigm discoveries.',
      timestamp: new Date().toISOString(),
      grounded_node_ids: ['node_1', 'node_2']
    }
  ],
  proj_vla: [
    {
      id: 'msg_vla_1',
      sender: 'agent',
      text: 'Project: VLA Policies & Flow Steering workspace initialized. Ask to synthesize action denoiser trajectories or generate a project report.',
      timestamp: new Date().toISOString(),
      grounded_node_ids: ['node_5', 'node_6']
    }
  ],
  proj_skeletal: [
    {
      id: 'msg_skel_1',
      sender: 'agent',
      text: 'Project: Skeletal Priors & Kinematics workspace initialized. Discuss joint limit loss terms or PhysCtrl MPC integration.',
      timestamp: new Date().toISOString(),
      grounded_node_ids: ['node_3', 'node_4']
    }
  ]
};

export const useMemexStore = create<MemexState>((set, get) => ({
  activeProjectId: 'global',
  nodes: [],
  edges: [],
  projects: [],
  chatHistory: initialDefaultChat,
  thinkingState: {
    isThinking: false,
    currentAction: 'Idle',
    visitedNodeIds: []
  },
  selectedNodeId: 'node_1',
  hoveredNodeId: null,
  searchQuery: '',
  selectedNodeTypeFilter: 'all',
  isVoiceListening: false,
  isLoading: false,

  setActiveProjectId: async (activeProjectId) => {
    set({ activeProjectId });
    await get().fetchGraphData();
  },
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
  setHoveredNodeId: (hoveredNodeId) => set({ hoveredNodeId }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setSelectedNodeTypeFilter: (selectedNodeTypeFilter) => set({ selectedNodeTypeFilter }),
  setVoiceListening: (isVoiceListening) => set({ isVoiceListening }),

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

  sendMessage: async (text, isVoice = false) => {
    const projId = get().activeProjectId;
    const userMsg: ChatMessage = {
      id: `user_msg_${Date.now()}`,
      sender: 'user',
      text,
      is_voice: isVoice,
      timestamp: new Date().toISOString()
    };

    // Update chat history for active project immediately
    const currentMsgs = get().chatHistory[projId] || [];
    set({
      chatHistory: {
        ...get().chatHistory,
        [projId]: [...currentMsgs, userMsg]
      },
      thinkingState: {
        isThinking: true,
        currentAction: `Agent evaluating query in ${projId}...`,
        visitedNodeIds: []
      }
    });

    try {
      const lower = text.toLowerCase();

      // Check if user is asking for a report
      if (lower.includes('report') || lower.includes('summary report')) {
        const reportRes = await fetch('/api/reports/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: `Synthesis Report: ${projId === 'global' ? 'Master Superset' : projId}`,
            target_node_ids: get().nodes.map(n => n.id),
            project_id: projId
          })
        });
        const reportData = await reportRes.json();

        const agentReportMsg: ChatMessage = {
          id: `agent_msg_${Date.now()}`,
          sender: 'agent',
          text: `Prepared interactive synthesis report for scope "${projId}":`,
          timestamp: new Date().toISOString(),
          grounded_node_ids: Object.values(reportData.provenance_mappings || {}) as string[],
          report: reportData
        };

        set({
          chatHistory: {
            ...get().chatHistory,
            [projId]: [...(get().chatHistory[projId] || []), agentReportMsg]
          },
          thinkingState: {
            isThinking: false,
            currentAction: 'Idle',
            visitedNodeIds: Object.values(reportData.provenance_mappings || {}) as string[]
          }
        });
        return;
      }

      // Check if user is pasting a URL or intake item
      if (lower.startsWith('http') || lower.includes('arxiv') || lower.includes('doi')) {
        const intakeRes = await fetch('/api/intake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_type: 'url',
            content_or_url: text,
            project_id: projId
          })
        });
        const intakeData = await intakeRes.json();
        await get().fetchGraphData();

        const agentIntakeMsg: ChatMessage = {
          id: `agent_msg_${Date.now()}`,
          sender: 'agent',
          text: `Ingested & bi-directionally linked URL. Extracted concept node "${intakeData.node?.title}".`,
          timestamp: new Date().toISOString(),
          grounded_node_ids: intakeData.seed_traversal || [intakeData.node?.id]
        };

        set({
          chatHistory: {
            ...get().chatHistory,
            [projId]: [...(get().chatHistory[projId] || []), agentIntakeMsg]
          },
          selectedNodeId: intakeData.node?.id,
          thinkingState: {
            isThinking: false,
            currentAction: 'Idle',
            visitedNodeIds: intakeData.seed_traversal || []
          }
        });
        return;
      }

      // Standard Chat / Insight Ingest
      const intakeRes = await fetch('/api/intake', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_type: isVoice ? 'voice' : 'text',
          content_or_url: text,
          project_id: projId
        })
      });
      const intakeData = await intakeRes.json();
      await get().fetchGraphData();

      const agentMsg: ChatMessage = {
        id: `agent_msg_${Date.now()}`,
        sender: 'agent',
        text: `Processed ${isVoice ? 'spoken insight' : 'thought'}. Updated Master Superset & linked to project "${projId}".`,
        timestamp: new Date().toISOString(),
        grounded_node_ids: intakeData.seed_traversal || []
      };

      set({
        chatHistory: {
          ...get().chatHistory,
          [projId]: [...(get().chatHistory[projId] || []), agentMsg]
        },
        selectedNodeId: intakeData.node?.id,
        thinkingState: {
          isThinking: false,
          currentAction: 'Idle',
          visitedNodeIds: intakeData.seed_traversal || []
        }
      });
    } catch (err) {
      console.error('Chat execution failed:', err);
      set({
        thinkingState: {
          isThinking: false,
          currentAction: 'Idle',
          visitedNodeIds: []
        }
      });
    }
  },

  createProjectWorkspace: async (name, description) => {
    const projId = `proj_${Date.now()}`;
    const newProj: ProjectWorkspace = {
      id: projId,
      name,
      description,
      node_ids: [],
      edge_ids: [],
      created_at: new Date().toISOString()
    };
    await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newProj)
    });
    await get().fetchProjects();
    await get().setActiveProjectId(projId);
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
  }
}));
