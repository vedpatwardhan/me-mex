import { create } from 'zustand';
import { AgentThinkingState, ChatMessage, GraphEdge, GraphNode, NodeType, ProjectWorkspace } from '../types';
import { voiceService } from '../services/voiceService';

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
  selectedNodeId: null,
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
        currentAction: `Executive Orchestrator evaluating query in ${projId}...`,
        visitedNodeIds: []
      }
    });

    try {
      const currentHistory = (get().chatHistory[projId] || []).map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: text,
          project_id: projId,
          is_voice: isVoice,
          chat_history: currentHistory,
        })
      });

      if (!res.ok || !res.body) {
        throw new Error(`Chat stream request failed: ${res.statusText}`);
      }

      // Initialize empty agent response bubble in the UI
      const agentMsgId = `agent_msg_${Date.now()}`;
      let accumulatedText = '';
      const touchedNodes: any[] = [];

      const initialAgentMsg: ChatMessage = {
        id: agentMsgId,
        sender: 'agent',
        text: '',
        timestamp: new Date().toISOString(),
        grounded_node_ids: [],
      };

      set({
        chatHistory: {
          ...get().chatHistory,
          [projId]: [...(get().chatHistory[projId] || []), initialAgentMsg]
        }
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          try {
            const eventData = JSON.parse(trimmed.slice(6));
            const evtType = eventData.event;

            if (evtType === 'token_chunk') {
              const delta = eventData.delta || '';
              accumulatedText += delta;

              // Update agent bubble text live
              set((state) => ({
                chatHistory: {
                  ...state.chatHistory,
                  [projId]: (state.chatHistory[projId] || []).map((m) =>
                    m.id === agentMsgId ? { ...m, text: accumulatedText } : m
                  )
                }
              }));
            } else if (evtType === 'chat_complete') {
              if (!accumulatedText && eventData.final_answer) {
                accumulatedText = eventData.final_answer;
                set((state) => ({
                  chatHistory: {
                    ...state.chatHistory,
                    [projId]: (state.chatHistory[projId] || []).map((m) =>
                      m.id === agentMsgId ? { ...m, text: accumulatedText } : m
                    )
                  }
                }));
              }
            } else if (evtType === 'node_touched') {
              touchedNodes.push(eventData);
            }
          } catch (e) {
            console.error('Error parsing SSE event:', e);
          }
        }
      }


      await get().fetchGraphData();

      set({
        thinkingState: {
          isThinking: false,
          currentAction: 'Idle',
          visitedNodeIds: touchedNodes.map((n: any) => n.node_id).filter(Boolean)
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
  }
}));
