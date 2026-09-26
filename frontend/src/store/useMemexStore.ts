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
      const sseUrl = `/api/sse/chat?query=${encodeURIComponent(text)}`;
      const eventSource = new EventSource(sseUrl);
      const visitedIdsSet = new Set<string>();

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const evtType = data.event;

          if (evtType === 'intent_classified') {
            set({
              thinkingState: {
                ...get().thinkingState,
                currentAction: `Intent classified: ${data.intent}`
              }
            });
          } else if (evtType === 'node_touched') {
            if (data.node_id) {
              visitedIdsSet.add(data.node_id);
              set({
                thinkingState: {
                  ...get().thinkingState,
                  currentAction: `Concept '${data.node_title || data.node_id}' touched by ${data.persona_name}`,
                  visitedNodeIds: Array.from(visitedIdsSet)
                }
              });
            }
          } else if (evtType === 'persona_traversal_active') {
            if (data.traversing_node_ids) {
              data.traversing_node_ids.forEach((id: string) => visitedIdsSet.add(id));
              set({
                thinkingState: {
                  ...get().thinkingState,
                  currentAction: `${data.department_name} traversing adjacent concepts...`,
                  visitedNodeIds: Array.from(visitedIdsSet)
                }
              });
            }
          } else if (evtType === 'persona_web_search') {
            set({
              thinkingState: {
                ...get().thinkingState,
                currentAction: `Executing DuckDuckGo web search: ${data.search_query}`
              }
            });
          } else if (evtType === 'orchestrator_tool_call') {
            set({
              thinkingState: {
                ...get().thinkingState,
                currentAction: `Invoking tool ${data.tool_name}...`
              }
            });
          } else if (evtType === 'tool_complete') {
            get().fetchGraphData();
            if (data.concept_id) {
              set({ selectedNodeId: data.concept_id });
            }
          } else if (evtType === 'chat_complete') {
            eventSource.close();
            const finalAnswer = data.final_answer || `Processed message.`;
            const agentMsg: ChatMessage = {
              id: `agent_msg_${Date.now()}`,
              sender: 'agent',
              text: finalAnswer,
              timestamp: new Date().toISOString(),
              grounded_node_ids: Array.from(visitedIdsSet)
            };

            if (isVoice && finalAnswer) {
              voiceService.speakText(finalAnswer);
            }

            set({
              chatHistory: {
                ...get().chatHistory,
                [projId]: [...(get().chatHistory[projId] || []), agentMsg]
              },
              thinkingState: {
                isThinking: false,
                currentAction: 'Idle',
                visitedNodeIds: Array.from(visitedIdsSet)
              }
            });
          }
        } catch (e) {
          console.error('[MemexStore] SSE parse error:', e);
        }
      };

      eventSource.onerror = (err) => {
        console.warn('[MemexStore] SSE Connection closed or error, falling back to POST /api/chat:', err);
        eventSource.close();

        // Fallback to standard POST /api/chat REST call if EventSource fails
        fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text, project_id: projId, is_voice: isVoice })
        })
          .then((res) => res.json())
          .then((chatData) => {
            get().fetchGraphData();
            const agentText = chatData.reply || 'Processed input successfully.';
            const agentMsg: ChatMessage = {
              id: `agent_msg_${Date.now()}`,
              sender: 'agent',
              text: agentText,
              timestamp: new Date().toISOString(),
              grounded_node_ids: (chatData.touched_nodes || []).map((n: any) => n.node_id)
            };

            if (isVoice && agentText) {
              voiceService.speakText(agentText);
            }

            set({
              chatHistory: {
                ...get().chatHistory,
                [projId]: [...(get().chatHistory[projId] || []), agentMsg]
              },
              thinkingState: {
                isThinking: false,
                currentAction: 'Idle',
                visitedNodeIds: (chatData.touched_nodes || []).map((n: any) => n.node_id)
              }
            });
          });
      };
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
      is_directional: true,
      text_body: 'User defined relationship link',
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
