import { useCallback, useEffect, useRef, useState } from "react";
import type { JobStatus } from "../types";

interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

interface UseJobStreamResult {
  events: SSEEvent[];
  status: JobStatus["status"] | null;
  stats: Record<string, number>;
  error: string | null;
}

export function useJobStream(jobId: string | null): UseJobStreamResult {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [status, setStatus] = useState<JobStatus["status"] | null>(null);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  useEffect(() => {
    if (!jobId) return;

    close();
    setEvents([]);
    setStatus("running");
    setStats({});
    setError(null);

    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as Record<string, unknown>;
        const event: SSEEvent = { type: e.type || "message", data: parsed };
        setEvents((prev) => [...prev, event]);
      } catch {
        /* ignore malformed */
      }
    };

    const handleTyped = (type: string) => (e: MessageEvent) => {
      try {
        const parsed = JSON.parse(e.data) as Record<string, unknown>;
        setEvents((prev) => [...prev, { type, data: parsed }]);

        if (type === "status") {
          const s = parsed.stats as Record<string, number> | undefined;
          if (s) setStats(s);
        }
        if (type === "done") {
          const s = parsed.stats as Record<string, number> | undefined;
          if (s) setStats(s);
          setStatus("done");
          close();
        }
        if (type === "error") {
          setError(String(parsed.message ?? "Unknown error"));
          setStatus("error");
          close();
        }
      } catch {
        /* ignore */
      }
    };

    for (const t of ["status", "new_url", "new_file", "secret", "done", "error"]) {
      es.addEventListener(t, handleTyped(t) as EventListener);
    }

    es.onerror = () => {
      setStatus("error");
      setError("SSE connection lost");
      close();
    };

    return close;
  }, [jobId, close]);

  return { events, status, stats, error };
}
