import { useEffect, useRef, useState, useCallback } from "react";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL || "/ws";

/**
 * Generic reconnecting websocket hook.
 * `path` e.g. "/dashboard/<workspaceId>/"
 * `onMessage(data)` called for every parsed JSON message.
 *
 * The hook will not attempt a connection until both `path` and a valid
 * access token are present. This prevents the empty-token reconnect loop
 * that occurs when a caller supplies a non-null path before the auth
 * token has been written to localStorage (e.g. Dashboard mounting before
 * AuthContext's async workspace resolution completes).
 */
export function useWebSocket(path, onMessage) {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  const attemptRef = useRef(0);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  // Read the token at the time `connect` is created so React can track it
  // as a dependency and re-create the callback (and therefore re-run the
  // effect) the moment a valid token appears in localStorage.
  const token = localStorage.getItem("sciq_access");

  const connect = useCallback(() => {
    // Guard: do not open a socket without both a path and a real token.
    // Treating a missing token the same as a missing path prevents the
    // backend from closing the connection with code 4403 and triggering
    // an infinite reconnect loop with an empty credential.
    if (!path || !token) return;

    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${WS_BASE}${path}?token=${token}`;
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      attemptRef.current = 0;
    };
    socket.onmessage = (event) => {
      try {
        onMessageRef.current?.(JSON.parse(event.data));
      } catch {
        // ignore malformed frames
      }
    };
    socket.onclose = () => {
      setConnected(false);
      const delay = Math.min(1000 * 2 ** attemptRef.current, 15000);
      attemptRef.current += 1;
      setTimeout(connect, delay);
    };
    socket.onerror = () => socket.close();
  }, [path, token]); // re-connect when path or token changes

  useEffect(() => {
    connect();
    return () => socketRef.current?.close();
  }, [connect]);

  const send = useCallback((data) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { connected, send };
}
