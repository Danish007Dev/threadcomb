'use client';

import { useEffect, useState } from 'react';
import { Activity, Loader2, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { API_BASE } from '../../../lib/api';

interface AgentAction {
  _id: string;
  agent: string;
  action_type: string;
  outcome: {
    result: string;
  };
  executed_at?: string;
}

export function ActivityFeedWidget() {
  const [activities, setActivities] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/activity/recent`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setActivities(data);
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="tc-card p-6 flex items-center justify-center min-h-[160px]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="tc-card p-6">
      <div className="flex items-center gap-3 mb-6">
        <Activity className="w-5 h-5 text-primary" />
        <h3 className="font-medium text-lg text-foreground">Recent Activity</h3>
      </div>

      <div className="space-y-4">
        {activities.map((action) => {
          let StatusIcon = Clock;
          let statusColor = "text-amber-500";
          if (action.outcome.result === 'success') {
            StatusIcon = CheckCircle2;
            statusColor = "text-emerald-500";
          } else if (action.outcome.result === 'failed') {
            StatusIcon = XCircle;
            statusColor = "text-rose-500";
          }

          let agentColor = "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400";
          if (action.agent === 'deal_chief') agentColor = "bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-400";
          if (action.agent === 'revenue_guardian') agentColor = "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-400";

          return (
            <div key={action._id} className="flex gap-4">
              <div className="mt-1">
                <StatusIcon className={`w-5 h-5 ${statusColor}`} />
              </div>
              <div className="flex-1 pb-4 border-b border-slate-100 dark:border-border/60 last:border-0 last:pb-0">
                <div className="flex items-start justify-between">
                  <div>
                    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider mb-1.5 ${agentColor}`}>
                      {action.agent.replace('_', ' ')}
                    </span>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-200">
                      {action.action_type.replace(/_/g, ' ')}
                    </p>
                  </div>
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    {action.executed_at ? new Date(action.executed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: 'numeric' }) : 'Unknown'}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
        {activities.length === 0 && (
          <p className="text-sm text-slate-400 text-center py-4">No recent activity.</p>
        )}
      </div>
    </div>
  );
}
