/**
 * SSE 订阅与事件恢复（PR-011）。
 *
 * 行动事件流首选 SSE（设计文档 §10）；断线恢复分两步：
 * 1) 用游标接口补齐错过的行动事件（fetchEvents(since)）；
 * 2) 以新的游标重建 EventSource。
 */
import { agentApi } from "./agent-client";

export type SessionEvent = {
  seq: number;
  turn: number;
  action_type: string;
  tool_name: string | null;
  status: string;
  summary: string;
};

export type EventSubscription = {
  close: () => void;
};

export function subscribeSessionEvents(
  sessionId: string,
  onEvents: (events: SessionEvent[]) => void,
  onError?: (error: unknown) => void,
): EventSubscription {
  let cursor = 0;
  let closed = false;
  let source: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const replayMissed = async () => {
    try {
      const { events, next_since } = await agentApi.fetchEvents(sessionId, cursor);
      if (events.length > 0) {
        cursor = next_since;
        onEvents(events);
      }
    } catch (error) {
      onError?.(error);
    }
  };

  const connect = () => {
    if (closed) return;
    source = new EventSource(
      `${process.env.NEXT_PUBLIC_AGENT_API_URL ?? "http://localhost:8001"}` +
        `/api/v1/agent/sessions/${sessionId}/events?since=${cursor}`,
    );
    source.addEventListener("action", (raw) => {
      try {
        const event = JSON.parse((raw as MessageEvent).data) as SessionEvent;
        cursor = Math.max(cursor, event.seq);
        onEvents([event]);
      } catch (error) {
        onError?.(error);
      }
    });
    source.onerror = () => {
      // 断线恢复：补齐缺口后重连
      source?.close();
      source = null;
      if (closed) return;
      reconnectTimer = setTimeout(async () => {
        await replayMissed();
        connect();
      }, 1500);
    };
  };

  void replayMissed().then(connect);

  return {
    close: () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      source?.close();
      source = null;
    },
  };
}
