import { create } from 'zustand';
import { AgentThinkingState, ChatMessage, GraphEdge, GraphNode, NodeType, NodeTypeFilter, ProjectWorkspace } from '../types';
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
  selectedNodeTypeFilter: NodeTypeFilter;
  isVoiceListening: boolean;
  isLoading: boolean;

  // Actions
  setActiveProjectId: (projectId: string) => Promise<void>;
  setSelectedNodeId: (id: string | null) => void;
  setHoveredNodeId: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setSelectedNodeTypeFilter: (filter: NodeTypeFilter) => void;
  setVoiceListening: (listening: boolean) => void;

  // API Async Actions
  fetchGraphData: () => Promise<void>;
  fetchProjects: () => Promise<void>;
  fetchChatHistory: () => Promise<void>;
  clearChatHistory: () => Promise<void>;
  sendMessage: (text: string, isVoice?: boolean) => Promise<void>;
  createProjectWorkspace: (name: string, description: string) => Promise<void>;
}

const initialDefaultChat: Record<string, ChatMessage[]> = {};

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
    await Promise.all([get().fetchGraphData(), get().fetchChatHistory()]);
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
      const rawEdges = data.edges || [];
      const normalizedEdges = rawEdges.map((e: any) => ({
        ...e,
        source: e.source ?? e.source_id ?? e.source_node_id,
        target: e.target ?? e.target_id ?? e.target_node_id,
      }));
      set({ nodes: data.nodes || [], edges: normalizedEdges });
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

  fetchChatHistory: async () => {
    const projId = get().activeProjectId;
    try {
      const res = await fetch(`/api/projects/${projId}/chat`);
      if (res.ok) {
        const msgs = await res.json();
        set({
          chatHistory: {
            ...get().chatHistory,
            [projId]: (msgs || []).map((m: any) => ({
              id: m._id || m.id || `msg_${Date.now()}`,
              sender: m.sender || 'agent',
              text: m.text || '',
              is_voice: m.is_voice || false,
              timestamp: m.created_at ? new Date(m.created_at * 1000).toISOString() : new Date().toISOString(),
              grounded_node_ids: m.grounded_node_ids || []
            }))
          }
        });
      }
    } catch (err) {
      console.error(`Failed to fetch chat history for ${projId}:`, err);
    }
  },

  clearChatHistory: async () => {
    const projId = get().activeProjectId;
    try {
      const res = await fetch(`/api/projects/${projId}/chat`, {
        method: 'DELETE'
      });
      if (res.ok) {
        set({
          chatHistory: {
            ...get().chatHistory,
            [projId]: []
          }
        });
      }
    } catch (err) {
      console.error(`Failed to clear chat history for ${projId}:`, err);
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
      const accumulatedEvents: string[] = [];
      const touchedNodes: any[] = [];

      const initialAgentMsg: ChatMessage = {
        id: agentMsgId,
        sender: 'agent',
        text: '',
        timestamp: new Date().toISOString(),
        grounded_node_ids: [],
        streaming_events: [],
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

            // Map and collect human-readable event descriptions for real-time chat display
            let logMsg = '';
            if (evtType === 'orchestrator_tool_call') {
              logMsg = `Executing tool: ${eventData.tool_name || 'action'}...`;
            } else if (evtType === 'tool_complete') {
              logMsg = eventData.message || 'Tool call completed.';
            } else if (evtType === 'passages_chunked') {
              logMsg = `Document chunked into ${eventData.total_chunks || 'multiple'} passages.`;
            } else if (evtType === 'passage_extraction_progress') {
              logMsg = `Extracting concepts: passage ${eventData.current_chunk}/${eventData.total_chunks}...`;
            } else if (evtType === 'passages_extracted') {
              logMsg = `Passage extractions complete: ${eventData.total_raw_concepts} raw concepts found.`;
            } else if (evtType === 'consolidation_start') {
              logMsg = `Consolidating concepts into canonical knowledge nodes...`;
            } else if (evtType === 'consolidation_complete') {
              logMsg = `Consolidated into ${eventData.canonical_concepts_count} canonical concepts.`;
            } else if (evtType === 'consolidation_failed') {
              logMsg = `Consolidation error: ${eventData.error || 'Failed'}`;
            } else if (evtType === 'root_node_created') {
              logMsg = `Created Document Root Node: "${eventData.title || ''}".`;
            } else if (evtType === 'intra_concepts_created') {
              logMsg = `Created ${eventData.count} intra-document concept nodes.`;
            } else if (evtType === 'hubs_calculated') {
              logMsg = `Identified ${eventData.count || 0} active community hubs for cross-linking.`;
            } else if (evtType === 'persona_traversal_start') {
              logMsg = eventData.message || `Specialist persona exploring sub-graph...`;
            } else if (evtType === 'ingestion_completed') {
              logMsg = eventData.message || `Document ingestion completed.`;
            }

            if (logMsg && !accumulatedEvents.includes(logMsg)) {
              accumulatedEvents.push(logMsg);
              set((state) => ({
                chatHistory: {
                  ...state.chatHistory,
                  [projId]: (state.chatHistory[projId] || []).map((m) =>
                    m.id === agentMsgId ? { ...m, streaming_events: [...accumulatedEvents] } : m
                  )
                },
                thinkingState: {
                  ...state.thinkingState,
                  currentAction: logMsg
                }
              }));
            }

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
