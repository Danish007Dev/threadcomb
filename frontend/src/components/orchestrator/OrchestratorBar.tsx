'use client';

import { useState, useRef, useEffect } from 'react';
import { Sparkles, ArrowRight, Loader2, CheckCircle2 } from 'lucide-react';
import { API_BASE } from '../../lib/api';
import { cn } from '../../lib/utils';

interface OrchestratorEvent {
  event: string;
  message?: string;
  agent?: string;
  confidence?: number;
  input?: string;
}

const SUGGESTION_CHIPS = [
  { label: 'Audit my emails' },
  { label: 'Chase overdue payments' },
  { label: 'Check pending deals' },
];

export function OrchestratorBar({ creatorId }: { creatorId?: string }) {
  const [input, setInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [events, setEvents] = useState<OrchestratorEvent[]>([]);
  const [isDone, setIsDone] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const handleSubmit = async (text?: string) => {
    const commandText = text || input.trim();
    if (!commandText || !creatorId) return;

    setEvents([]);
    setIsRunning(true);
    setIsDone(false);
    setInput(commandText);

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    // Try SSE first, fall back to POST
    try {
      const url = new URL(`${API_BASE}/orchestrate`);
      url.searchParams.append('input', commandText);

      const eventSource = new EventSource(url.toString(), {
        withCredentials: true,
      });
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data) as OrchestratorEvent;
          if (data.event === 'done') {
            setIsRunning(false);
            setIsDone(true);
            eventSource.close();
            eventSourceRef.current = null;
          } else {
            setEvents((prev) => [...prev, data]);
          }
        } catch {
          // Ignore malformed
        }
      };

      eventSource.onerror = async () => {
        eventSource.close();
        eventSourceRef.current = null;

        // Fall back to non-streaming endpoint
        try {
          const res = await fetch(`${API_BASE}/orchestrate/command`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: commandText }),
          });
          if (res.ok) {
            const data = await res.json();
            setEvents([{
              event: 'agent_complete',
              agent: data.routed_to,
              message: data.message,
              confidence: data.confidence,
            }]);
          }
        } catch {
          setEvents([{
            event: 'error',
            message: 'Failed to connect. Please try again.',
          }]);
        }
        setIsRunning(false);
        setIsDone(true);
      };
    } catch {
      setIsRunning(false);
      setIsDone(true);
    }
  };

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const latestEvent = events.length > 0 ? events[events.length - 1] : null;
  const routedAgents = events
    .filter((e) => e.event === 'agent_start' && e.agent)
    .map((e) => e.agent!);

  const agentLabels: Record<string, string> = {
    dna_reader: 'Email Audit',
    deal_chief: 'Deal Manager',
    revenue_guardian: 'Invoice Guardian',
  };

  return (
    <div className="tc-card p-4 md:p-5 space-y-3">
      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}
        className="flex gap-2"
      >
        <div className="relative flex-1">
          <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary/60" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask ThreadComb to audit, chase payments, or check deals..."
            className="w-full pl-10 pr-4 py-2.5 text-sm rounded-lg border border-border/60 bg-background
                       focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50
                       placeholder:text-muted-foreground/60 transition-all"
            disabled={isRunning}
            data-testid="orchestrator-input"
          />
        </div>
        <button
          type="submit"
          disabled={isRunning || !input.trim()}
          className={cn(
            'px-5 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2',
            isRunning
              ? 'bg-primary/70 text-primary-foreground cursor-wait'
              : 'bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed'
          )}
          data-testid="orchestrator-submit"
        >
          {isRunning ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Running
            </>
          ) : (
            <>
              <ArrowRight className="w-3.5 h-3.5" />
              Run
            </>
          )}
        </button>
      </form>

      {/* Suggestion chips — show when idle */}
      {!isRunning && events.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTION_CHIPS.map((chip) => (
            <button
              key={chip.label}
              onClick={() => handleSubmit(chip.label)}
              className="px-3 py-1.5 text-xs font-medium rounded-full border border-border/60
                         text-muted-foreground hover:text-foreground hover:border-primary/40
                         hover:bg-primary/5 transition-all flex items-center gap-1.5"
              data-testid={`chip-${chip.label.replace(/\s/g, '-').toLowerCase()}`}
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Status output */}
      {events.length > 0 && (
        <div className="rounded-lg border border-border/40 bg-muted/20 p-3 space-y-2">
          {/* Latest message */}
          <div className="flex items-center gap-3">
            {isRunning ? (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-primary" />
              </span>
            ) : isDone ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
            ) : null}
            <p className="text-sm text-foreground font-medium">
              {latestEvent?.message || 'Processing...'}
            </p>
          </div>

          {/* Agent pills */}
          {routedAgents.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-1">
              {routedAgents.map((agent, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium
                             rounded-full bg-primary/10 text-primary"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                  {agentLabels[agent] || agent.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          )}

          {/* Done state — navigation hints */}
          {isDone && routedAgents.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              Tasks are running in the background. The dashboard will update automatically.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
