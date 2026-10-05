// A WebSocket that reconnects with backoff. Messages sent while disconnected are DROPPED, never
// queued: replaying stale input into a live game session is worse than losing it.

export type SocketHandlers = {
  onOpen?: () => void;
  onClose?: () => void;
  onText?: (text: string) => void;
  onBinary?: (data: Blob) => void;
};

export class ReconnectingSocket {
  private ws: WebSocket | null = null;
  private closed = false;
  private retryMs = 500;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly url: string,
    private readonly handlers: SocketHandlers,
  ) {
    this.connect();
  }

  private connect(): void {
    const ws = new WebSocket(this.url);
    ws.binaryType = "blob";
    ws.onopen = () => {
      this.retryMs = 500;
      this.handlers.onOpen?.();
    };
    ws.onmessage = (event: MessageEvent<string | Blob>) => {
      if (typeof event.data === "string") this.handlers.onText?.(event.data);
      else this.handlers.onBinary?.(event.data);
    };
    ws.onclose = () => {
      this.ws = null;
      this.handlers.onClose?.();
      if (!this.closed) {
        this.timer = setTimeout(() => this.connect(), this.retryMs);
        this.retryMs = Math.min(this.retryMs * 2, 8000);
      }
    };
    this.ws = ws;
  }

  send(message: object): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(message));
    return true;
  }

  /** Drop the current socket and reconnect (the usual backoff): for a link that stays "open" but
   * delivers nothing, e.g. a tab Safari throttled (2026-10-05). */
  kick(): void {
    this.ws?.close();
  }

  close(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
  }
}

/** http(s)://host:port of the backend: the configured public URL, else this page's host on :8000.
 * Browser only (reads window.location). */
export function backendHttpBase(configured: string | null): string {
  const http = configured ?? `${window.location.protocol}//${window.location.hostname}:8000`;
  return http.replace(/\/+$/, "");
}

/** ws(s)://host:port of the backend (see backendHttpBase). */
export function backendWsBase(configured: string | null): string {
  return backendHttpBase(configured).replace(/^http/, "ws");
}
