import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, API_BASE } from "@/lib/api-client";

interface WsTokenOut {
  wsToken: string;
  expiresInSeconds: number;
}

/**
 * Opens the real `/ws?token=...` socket (backend/app/api/ws_endpoint.py):
 * fetches a short-lived (60s) single-purpose token via
 * `GET /api/v1/ws/token`, then connects. On `document.uploaded` /
 * `document.processed` events it invalidates the document-queue query so
 * the "Recent uploads" panel updates live instead of requiring a manual
 * refresh -- this is the wiring the architecture doc flagged as the
 * biggest real gap in applicant.upload.tsx.
 */
export function useDocumentWebSocket(applicationId?: string) {
  const qc = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;

    async function connect() {
      try {
        const { wsToken } = await api.get<WsTokenOut>("/ws/token");
        if (cancelled) return;
        const wsBase = API_BASE.replace(/^http/, "ws");
        const url = new URL(`${wsBase}/ws`);
        url.searchParams.set("token", wsToken);
        if (applicationId) url.searchParams.set("application_id", applicationId);

        socket = new WebSocket(url.toString());
        socketRef.current = socket;

        socket.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data);
            if (
              data.type === "document.uploaded" ||
              data.type === "document.processed" ||
              // Session 12: fired once per pipeline sub-stage (see
              // app/background/tasks.py's `_notify_stage`) so the
              // "Uploading -> Reading document -> Extracting text ->
              // Extracting fields -> Running validation -> Finished"
              // progress line updates live, not just at the two
              // start/end events above.
              data.type === "document.stage"
            ) {
              qc.invalidateQueries({ queryKey: ["applicant", "documents"] });
              // Evidence Checklist addition: the same two events drive the
              // Evidence Strength card and per-category completion bars,
              // so they need the same live-invalidation treatment as the
              // original "Recent uploads" panel above -- this is what
              // makes "updates live as uploads are processed" (the
              // product's own stated addition) actually true rather than
              // only true after a manual refresh.
              qc.invalidateQueries({ queryKey: ["applicant", "evidence", "checklist"] });
              qc.invalidateQueries({ queryKey: ["applicant", "evidence", "wallet"] });
            }
            if (data.type === "notification.created") {
              qc.invalidateQueries({ queryKey: ["notifications"] });
            }
          } catch {
            // Non-JSON / unrecognized frame -- ignore rather than crash the socket handler.
          }
        };
      } catch {
        // Token fetch or socket construction failed (e.g. not authenticated
        // yet) -- the upload panel still works via the initial query fetch
        // and mutation-triggered invalidation, just without live push.
      }
    }

    connect();
    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [applicationId, qc]);

  return socketRef;
}
