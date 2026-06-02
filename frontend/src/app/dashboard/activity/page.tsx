'use client';

import { useEffect, useState } from 'react';
import { Loader2, Activity, Filter, Download, ChevronDown, ChevronUp } from 'lucide-react';
import { API_BASE, getMe } from '../../../lib/api';
import type { Creator } from '../../../lib/types';

interface AgentAction {
  _id: string;
  agent: string;
  action_type: string;
  outcome: {
    result: string;
    [key: string]: any;
  };
  decision?: any;
  flags_raised?: string[];
  executed_at?: string;
  confidence?: number;
}

export default function ActivityAuditPage() {
  const [activities, setActivities] = useState<AgentAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const url = new URL(`${API_BASE}/activity/all`);
        if (agentFilter !== 'all') url.searchParams.append('agent', agentFilter);
        if (outcomeFilter !== 'all') url.searchParams.append('outcome', outcomeFilter);

        const res = await fetch(url.toString(), { credentials: 'include' });
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
  }, [agentFilter, outcomeFilter]);

  const handleExportJson = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(activities, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", `threadcomb_activity_export_${new Date().getTime()}.json`);
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  return (
    <div className="min-h-dvh bg-slate-50 px-6 py-8 md:px-10">
      <div className="max-w-5xl mx-auto">
        <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
              <Activity className="w-6 h-6 text-primary" /> Agent Action Audit
            </h1>
            <p className="text-slate-500 mt-2">
              A complete, transparent log of every action taken by your ThreadComb agents.
            </p>
          </div>
          <button
            onClick={handleExportJson}
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-lg text-sm font-medium hover:bg-slate-50 transition-colors shadow-sm"
          >
            <Download className="w-4 h-4" /> Export JSON
          </button>
        </header>

        <div className="tc-card mb-6 p-4 flex flex-wrap gap-4 items-center bg-white border-b-0 rounded-b-none border-slate-200">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <span className="text-sm font-medium text-slate-700">Filters:</span>
          </div>
          
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="text-sm border border-slate-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="all">All Agents</option>
            <option value="dna_reader">DNA Reader</option>
            <option value="deal_chief">Deal Chief</option>
            <option value="revenue_guardian">Revenue Guardian</option>
          </select>

          <select
            value={outcomeFilter}
            onChange={(e) => setOutcomeFilter(e.target.value)}
            className="text-sm border border-slate-300 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/20"
          >
            <option value="all">All Outcomes</option>
            <option value="success">Success</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <div className="tc-card rounded-t-none border-t-0 overflow-hidden bg-white">
          {loading ? (
            <div className="p-12 flex justify-center">
              <Loader2 className="w-8 h-8 animate-spin text-slate-300" />
            </div>
          ) : activities.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              No actions found matching your filters.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {activities.map((action) => (
                <div key={action._id} className="flex flex-col">
                  <div 
                    className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50 transition-colors"
                    onClick={() => setExpandedId(expandedId === action._id ? null : action._id)}
                  >
                    <div className="flex items-center gap-4 flex-1 min-w-0">
                      <div className="w-32 shrink-0">
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                          {action.agent.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="flex-1 truncate">
                        <span className="text-sm font-medium text-slate-900">
                          {action.action_type.replace(/_/g, ' ')}
                        </span>
                        {action.confidence && (
                          <span className="ml-3 text-xs text-slate-400">
                            Conf: {(action.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      <div className="w-24 shrink-0 text-right">
                        <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                          action.outcome.result === 'success' ? 'bg-emerald-100 text-emerald-700' :
                          action.outcome.result === 'failed' ? 'bg-rose-100 text-rose-700' :
                          'bg-amber-100 text-amber-700'
                        }`}>
                          {action.outcome.result}
                        </span>
                      </div>
                      <div className="w-32 shrink-0 text-right text-xs text-slate-400">
                        {action.executed_at ? new Date(action.executed_at).toLocaleString() : ''}
                      </div>
                      <div className="shrink-0 text-slate-400">
                        {expandedId === action._id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </div>
                    </div>
                  </div>
                  
                  {expandedId === action._id && (
                    <div className="p-4 bg-slate-50/50 border-t border-slate-100 text-sm">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {action.decision && (
                          <div>
                            <h4 className="font-semibold text-slate-700 mb-2 text-xs uppercase tracking-wider">Decision Context</h4>
                            <pre className="bg-white p-3 rounded border border-slate-200 overflow-x-auto text-xs text-slate-600">
                              {JSON.stringify(action.decision, null, 2)}
                            </pre>
                          </div>
                        )}
                        <div>
                          <h4 className="font-semibold text-slate-700 mb-2 text-xs uppercase tracking-wider">Outcome Details</h4>
                          <pre className="bg-white p-3 rounded border border-slate-200 overflow-x-auto text-xs text-slate-600">
                            {JSON.stringify(action.outcome, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
