'use client';

import { useState, useRef, useEffect } from 'react';
import { API_BASE } from '../../lib/api';

interface OrchestratorEvent {
  event: string;
  message?: string;
  agent?: string;
  confidence?: number;
  input?: string;
}

export function OrchestratorBar({ creatorId }: { creatorId?: string }) {
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [events, setEvents] = useState<OrchestratorEvent[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !creatorId) return;

    // Reset state
    setEvents([]);
    setIsRunning(true);

    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = new URL(`${API_BASE}/orchestrate`);
    url.searchParams.append('input', input);

    const eventSource = new EventSource(url.toString(), {
      withCredentials: true,
    });
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data) as OrchestratorEvent;
        if (data.event === 'done') {
          setIsRunning(false);
          eventSource.close();
          eventSourceRef.current = null;
        } else {
          setEvents((prev) => [...prev, data]);
        }
      } catch {
        // Ignore malformed
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Error:', err);
      setIsRunning(false);
      eventSource.close();
      eventSourceRef.current = null;
    };
  };

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const latestEvent = events.length > 0 ? events[events.length - 1] : null;

  return (
    <div className="w-full bg-white rounded-lg shadow p-4 mb-6">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask ThreadComb to check deals, audit emails, or chase payments..."
          className="flex-1 px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={isRunning}
        />
        <button
          type="submit"
          disabled={isRunning || !input.trim()}
          className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {isRunning ? 'Running...' : 'Run'}
        </button>
      </form>
      
      {events.length > 0 && (
        <div className="mt-4 p-3 bg-slate-50 rounded border border-slate-100">
          <div className="flex items-center gap-3">
            {isRunning ? (
              <span className="flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
              </span>
            ) : (
              <span className="text-green-500">✓</span>
            )}
            <div className="text-sm text-slate-700 font-medium">
              {latestEvent?.message || 'Processing...'}
            </div>
          </div>
          
          <div className="mt-2 text-xs text-slate-500 flex gap-4">
            {events.map((evt, idx) => (
              evt.agent && evt.event === 'agent_start' && (
                <span key={idx} className="flex items-center gap-1">
                  <span className="text-blue-500">→</span>
                  {evt.agent.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </span>
              )
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
