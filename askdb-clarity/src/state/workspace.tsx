import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api, ApiError, type AskResponse, type ChatMessage, type Connection } from "@/lib/api";

const ACTIVE_KEY = "askdb.activeConnection";
const HISTORY_TURNS = 6;

export interface ChatTurn {
  id: string;
  question: string;
  status: "pending" | "done" | "error";
  response?: AskResponse;
  error?: string;
}

interface WorkspaceValue {
  connections: Connection[];
  connectionsLoading: boolean;
    offline: boolean;
  active: Connection | null;
  selectConnection: (id: string) => void;
  connectionAdded: (connection: Connection) => void;
  connectionRemoved: (id: string) => void;
  refetchConnections: () => void;

  turns: ChatTurn[];
  isAsking: boolean;
  ask: (question: string) => Promise<void>;
  clearChat: () => void;

  sqlDraft: string;
  setSqlDraft: (sql: string) => void;
  askDraft: string;
  setAskDraft: (text: string) => void;
    tableFocus: string | null;
  setTableFocus: (table: string | null) => void;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

function buildHistory(turns: ChatTurn[]): ChatMessage[] {
  const messages: ChatMessage[] = [];
  for (const turn of turns.slice(-HISTORY_TURNS)) {
    const response = turn.response;
    if (turn.status !== "done" || !response || response.status !== "success") continue;
    messages.push({ role: "user", content: turn.question });
    messages.push({
      role: "assistant",
      content: response.answer ?? "",
      ...(response.sql ? { sql: response.sql } : {}),
    });
  }
  return messages;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [chats, setChats] = useState<Record<string, ChatTurn[]>>({});
  const [sqlDraft, setSqlDraft] = useState("");
  const [askDraft, setAskDraft] = useState("");
  const [tableFocus, setTableFocus] = useState<string | null>(null);

  // Restore the last active connection after mount (never during SSR render).
  useEffect(() => {
    try {
      setActiveId(window.localStorage.getItem(ACTIVE_KEY));
    } catch {
      /* storage unavailable */
    }
  }, []);

  const connectionsQuery = useQuery({
    queryKey: ["connections"],
    queryFn: api.listConnections,
    retry: false,
    refetchOnWindowFocus: true,
  });
  const connections = useMemo(() => connectionsQuery.data ?? [], [connectionsQuery.data]);
  const offline = connectionsQuery.error instanceof ApiError && connectionsQuery.error.isOffline;

  const active = useMemo(
    () => connections.find((c) => c.connection_id === activeId) ?? connections[0] ?? null,
    [connections, activeId],
  );
  const activeIdRef = useRef<string | null>(null);
  activeIdRef.current = active?.connection_id ?? null;

  const selectConnection = useCallback((id: string) => {
    setActiveId(id);
    try {
      window.localStorage.setItem(ACTIVE_KEY, id);
    } catch {
          }
  }, []);

  const connectionAdded = useCallback(
    (connection: Connection) => {
      queryClient.setQueryData<Connection[]>(["connections"], (prev) => [...(prev ?? []), connection]);
      selectConnection(connection.connection_id);
    },
    [queryClient, selectConnection],
  );

  const connectionRemoved = useCallback(
    (id: string) => {
      queryClient.setQueryData<Connection[]>(["connections"], (prev) => (prev ?? []).filter((c) => c.connection_id !== id));
      queryClient.removeQueries({ predicate: (q) => q.queryKey[1] === id });
      setChats((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    },
    [queryClient],
  );

  const refetchConnections = useCallback(() => {
    void connectionsQuery.refetch();
  }, [connectionsQuery]);

  
  const chatsRef = useRef(chats);
  chatsRef.current = chats;

  const patchTurn = useCallback((connectionId: string, turnId: string, patch: Partial<ChatTurn>) => {
    setChats((prev) => ({
      ...prev,
      [connectionId]: (prev[connectionId] ?? []).map((t) => (t.id === turnId ? { ...t, ...patch } : t)),
    }));
  }, []);

  const ask = useCallback(
    async (question: string) => {
      const connectionId = activeIdRef.current;
      const text = question.trim();
      if (!connectionId || !text) return;

      const turnId = uid();
      const history = buildHistory(chatsRef.current[connectionId] ?? []);
      setChats((prev) => ({
        ...prev,
        [connectionId]: [...(prev[connectionId] ?? []), { id: turnId, question: text, status: "pending" }],
      }));

      try {
        const response = await api.chat({
          connection_id: connectionId,
          question: text,
          ...(history.length ? { history } : {}),
        });
        patchTurn(connectionId, turnId, { status: "done", response });
      } catch (error) {
        const message = error instanceof Error ? error.message : "Something went wrong.";
        patchTurn(connectionId, turnId, { status: "error", error: message });
        if (error instanceof ApiError && error.status === 404) void connectionsQuery.refetch();
      } finally {
        void queryClient.invalidateQueries({ queryKey: ["history", connectionId] });
        void queryClient.invalidateQueries({ queryKey: ["overview", connectionId] });
      }
    },
    [connectionsQuery, patchTurn, queryClient],
  );

  const clearChat = useCallback(() => {
    const id = activeIdRef.current;
    if (!id) return;
    setChats((prev) => ({ ...prev, [id]: [] }));
  }, []);

  const turns = useMemo(() => (active ? (chats[active.connection_id] ?? []) : []), [active, chats]);
  const isAsking = turns.some((t) => t.status === "pending");

  const value = useMemo<WorkspaceValue>(
    () => ({
      connections,
      connectionsLoading: connectionsQuery.isPending,
      offline,
      active,
      selectConnection,
      connectionAdded,
      connectionRemoved,
      refetchConnections,
      turns,
      isAsking,
      ask,
      clearChat,
      sqlDraft,
      setSqlDraft,
      askDraft,
      setAskDraft,
      tableFocus,
      setTableFocus,
    }),
    [
      connections, connectionsQuery.isPending, offline, active, selectConnection, connectionAdded,
      connectionRemoved, refetchConnections, turns, isAsking, ask, clearChat, sqlDraft, askDraft, tableFocus,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside <WorkspaceProvider>");
  return ctx;
}
