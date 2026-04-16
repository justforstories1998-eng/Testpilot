/* =================================================================
   TESTPILOT — WEBSOCKET HOOK FOR STREAMING CHAT
   ================================================================= */

import { useEffect, useRef, useCallback, useState } from 'react';

type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface ChatWsCallbacks {
  onToken?: (content: string) => void;
  onComplete?: (content: string) => void;
  onError?: (content: string) => void;
  onAck?: (message: string) => void;
}

interface UseChatWebSocketOptions {
  sessionId: string | null;
  callbacks: ChatWsCallbacks;
  autoConnect?: boolean;
}

export function useChatWebSocket({
  sessionId,
  callbacks,
  autoConnect = true,
}: UseChatWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const maxRetries = 5;
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [status, setStatus] = useState<WsStatus>('disconnected');

  const callbacksRef = useRef(callbacks);
  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  const connect = useCallback(() => {
    if (!sessionId) return;

    // Close existing connection
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* ignore */
      }
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/chat/${sessionId}`;

    setStatus('connecting');
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('connected');
      retriesRef.current = 0;

      // Keepalive ping
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ content: 'ping' }));
        }
      }, 25000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const type = msg.type as string;
        const cb = callbacksRef.current;

        switch (type) {
          case 'token':
            cb.onToken?.(msg.content || '');
            break;
          case 'complete':
            cb.onComplete?.(msg.content || '');
            break;
          case 'error':
            cb.onError?.(msg.content || 'Unknown error');
            break;
          case 'ack':
            cb.onAck?.(msg.message || '');
            break;
          case 'pong':
            break;
          case 'state_update':
            cb.onComplete?.('');
            break;
          default:
            break;
        }
      } catch {
        /* ignore malformed messages */
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      // Auto-reconnect with backoff
      if (autoConnect && retriesRef.current < maxRetries) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 15000);
        retriesRef.current += 1;
        setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      setStatus('error');
    };
  }, [sessionId, autoConnect]);

  const disconnect = useCallback(() => {
    retriesRef.current = maxRetries + 1; // prevent reconnect
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  const sendMessage = useCallback(
    (content: string, targetUrl?: string) => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({
            content,
            target_url: targetUrl || undefined,
          })
        );
        return true;
      }
      return false;
    },
    []
  );

  useEffect(() => {
    if (autoConnect && sessionId) {
      connect();
    }
    return () => disconnect();
  }, [sessionId, autoConnect, connect, disconnect]);

  return {
    status,
    sendMessage,
    disconnect,
    reconnect: connect,
    isConnected: status === 'connected',
  };
}

/* ---- Legacy test-run WebSocket (kept for compatibility) ---- */
export function useTestRunWebSocket(testRunId: string | null) {
  const [status, setStatus] = useState<WsStatus>('disconnected');

  useEffect(() => {
    if (!testRunId) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/test-run/${testRunId}`;

    const ws = new WebSocket(url);
    ws.onopen = () => setStatus('connected');
    ws.onclose = () => setStatus('disconnected');
    ws.onerror = () => setStatus('error');

    return () => {
      ws.close();
    };
  }, [testRunId]);

  return { status };
}