'use client';

import { useEffect, useState } from 'react';
import { API_BASE } from '../../../lib/api';
import { BarChart3 } from 'lucide-react';

interface DigestData {
  paid_this_week_inr: number;
  paid_count: number;
  outstanding_inr: number;
  overdue_count: number;
  followups_sent: number;
  message: string;
}

export function WeeklyDigestWidget({ creatorId }: { creatorId?: string }) {
  const [data, setData] = useState<DigestData | null>(null);

  useEffect(() => {
    if (!creatorId) return;

    // We can listen to the SSE for weekly digest here
    const eventSource = new EventSource(`${API_BASE}/sse/ingestion/${creatorId}`, {
      withCredentials: true,
    });

    eventSource.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.event === 'weekly_digest') {
          setData(parsed);
        }
      } catch {
        // ignore
      }
    };

    return () => {
      eventSource.close();
    };
  }, [creatorId]);

  if (!data) {
    return (
      <div className="tc-card p-6 flex flex-col items-center justify-center text-slate-400 min-h-[160px]">
        <BarChart3 className="w-8 h-8 mb-2 opacity-50" />
        <p className="text-sm">Waiting for your weekly digest...</p>
      </div>
    );
  }

  return (
    <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl p-6 text-white shadow-lg">
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="w-5 h-5 text-indigo-100" />
        <h3 className="font-medium text-lg text-indigo-50">Weekly Digest</h3>
      </div>
      
      <p className="text-indigo-100 mb-6">{data.message}</p>
      
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white/10 rounded-lg p-4 backdrop-blur-sm border border-white/10">
          <p className="text-indigo-200 text-sm mb-1">Paid This Week</p>
          <p className="text-2xl font-semibold">₹{data.paid_this_week_inr.toLocaleString('en-IN')}</p>
          <p className="text-xs text-indigo-300 mt-1">{data.paid_count} invoices</p>
        </div>
        
        <div className="bg-white/10 rounded-lg p-4 backdrop-blur-sm border border-white/10">
          <p className="text-indigo-200 text-sm mb-1">Still Outstanding</p>
          <p className="text-2xl font-semibold">₹{data.outstanding_inr.toLocaleString('en-IN')}</p>
          <p className="text-xs text-indigo-300 mt-1">{data.overdue_count} overdue</p>
        </div>

        <div className="bg-white/10 rounded-lg p-4 backdrop-blur-sm border border-white/10">
          <p className="text-indigo-200 text-sm mb-1">Follow-ups Sent</p>
          <p className="text-2xl font-semibold">{data.followups_sent}</p>
          <p className="text-xs text-indigo-300 mt-1">this week</p>
        </div>
      </div>
    </div>
  );
}
