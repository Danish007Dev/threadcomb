'use client';

import { useEffect, useMemo, useState } from 'react';
import { API_BASE } from '../lib/api';

export interface IngestionEvent {
  event: string;
  message?: string;
  count?: number;
  passed?: number;
  failed?: number;
  total?: number;
  passed_gate?: number;
  failed_gate?: number;
  hitl_queue?: number;
}

export interface IngestionStatusSnapshot {
  status: string;
  total_threads_found: number;
  threads_passed_gate: number;
  threads_queued_for_extraction: number;
  threads_extraction_complete: number;
  error_message?: string | null;
  started_at?: string | null;
  duration_seconds?: number | null;
}

export function useIngestionStatus(creatorId?: string, jobId?: string) {
  const [events, setEvents] = useState<IngestionEvent[]>([]);
  const [statusSnapshot, setStatusSnapshot] = useState<IngestionStatusSnapshot | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!creatorId) return;

    const eventSource = new EventSource(`${API_BASE}/sse/ingestion/${creatorId}`, {
      withCredentials: true,
    });

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as IngestionEvent;
        setEvents((prev) => [...prev, data]);
      } catch {
        // Ignore malformed events.
      }
    };

    eventSource.onerror = async () => {
      setIsConnected(false);
      if (!jobId) return;

      try {
        const res = await fetch(`${API_BASE}/ingestion/status/${jobId}`, {
          credentials: 'include',
        });
        if (!res.ok) return;
        const status = (await res.json()) as IngestionStatusSnapshot;
        setStatusSnapshot(status);
        setEvents((prev) => [
          ...prev,
          {
            event: 'status_recovery',
            message: `Reconnected. Current state: ${status.status}`,
            passed: status.threads_passed_gate,
            total: status.total_threads_found,
          },
        ]);
      } catch (err) {
        console.error('Status recovery failed:', err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [creatorId, jobId]);

  const latestEvent = useMemo(
    () => (events.length > 0 ? events[events.length - 1] : null),
    [events]
  );

  return {
    events,
    latestEvent,
    statusSnapshot,
    isConnected,
  };
}
