'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Settings,
  ArrowLeft,
  Download,
  Trash2,
  Loader2,
  Shield,
  User,
  Mail,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

import { Button } from '../../../components/ui/button';
import { ThreadCombLogo } from '../../../components/brand/Logo';
import { cn } from '../../../lib/utils';
import { getMe, exportSkillsMap, deleteAccount, logout } from '../../../lib/api';
import type { Creator } from '../../../lib/types';

export default function SettingsPage() {
  const router = useRouter();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await getMe();
        if (!cancelled) setCreator(me);
      } catch {
        if (!cancelled) router.replace('/login');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [router]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await exportSkillsMap();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `threadcomb_export_${creator?.creator_id?.slice(0, 8) || 'data'}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setExportSuccess(true);
      setTimeout(() => setExportSuccess(false), 3000);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (deleteConfirmText !== 'DELETE') return;
    setDeleting(true);
    try {
      await deleteAccount();
      await logout();
      router.replace('/login');
    } catch (err) {
      console.error('Delete failed:', err);
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-dvh flex items-center justify-center">
        <div className="w-8 h-8 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-dvh bg-background" data-testid="settings-page">
      {/* Header */}
      <header className="border-b border-border/40 bg-card/60 backdrop-blur-sm px-6 md:px-10 py-5">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/dashboard')}
              className="text-muted-foreground hover:text-foreground transition-colors"
              data-testid="back-to-dashboard"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <ThreadCombLogo className="text-primary" />
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 md:px-10 py-8 space-y-8">
        {/* Page title */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary">
              <Settings className="w-5 h-5" />
            </div>
            <h1 className="font-heading text-2xl md:text-3xl tracking-tight font-medium text-foreground">
              Settings
            </h1>
          </div>
        </div>

        {/* Profile Section */}
        <section className="tc-card p-6 space-y-4">
          <div className="flex items-center gap-3 mb-4">
            <User className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-medium text-foreground uppercase tracking-wider">Profile</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Name</label>
              <div className="text-sm font-medium text-foreground bg-muted/30 rounded-lg px-3 py-2.5">
                {creator?.name || '—'}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Email</label>
              <div className="text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2.5 flex items-center gap-2">
                <Mail className="w-3.5 h-3.5 text-muted-foreground" />
                {creator?.email || '—'}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Platform</label>
              <div className="text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2.5 capitalize">
                {creator?.platform_primary || '—'}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Niche</label>
              <div className="text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2.5 capitalize">
                {creator?.niche || '—'}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Gmail Connected</label>
              <div className="text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2.5 flex items-center gap-2">
                {creator?.gmail_connected ? (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    Connected
                  </>
                ) : (
                  <>
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                    Not connected
                  </>
                )}
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-1">Follower Tier</label>
              <div className="text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2.5">
                {creator?.follower_tier || '—'}
              </div>
            </div>
          </div>
        </section>

        {/* Data Export Section */}
        <section className="tc-card p-6 space-y-4">
          <div className="flex items-center gap-3 mb-2">
            <Shield className="w-4 h-4 text-muted-foreground" />
            <h2 className="text-sm font-medium text-foreground uppercase tracking-wider">Data & Privacy</h2>
          </div>
          <p className="text-sm text-muted-foreground">
            Under DPDP compliance, you have the right to export all your personal data or permanently delete your account.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <Button
              variant="outline"
              onClick={handleExport}
              disabled={exporting}
              data-testid="export-data-btn"
            >
              {exporting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Exporting...
                </>
              ) : exportSuccess ? (
                <>
                  <CheckCircle2 className="w-4 h-4 mr-2 text-emerald-500" />
                  Downloaded!
                </>
              ) : (
                <>
                  <Download className="w-4 h-4 mr-2" />
                  Export My Data
                </>
              )}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            Exports your profile, deals, invoices, skills map, and audit reports as a JSON file.
          </p>
        </section>

        {/* Danger Zone */}
        <section className="tc-card p-6 space-y-4 border-red-200 dark:border-red-900">
          <div className="flex items-center gap-3 mb-2">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            <h2 className="text-sm font-medium text-red-600 dark:text-red-400 uppercase tracking-wider">Danger Zone</h2>
          </div>

          {!showDeleteConfirm ? (
            <div>
              <p className="text-sm text-muted-foreground mb-4">
                Permanently delete your account and all associated data. This action cannot be undone.
              </p>
              <Button
                variant="outline"
                onClick={() => setShowDeleteConfirm(true)}
                className="border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/20"
                data-testid="delete-account-btn"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete My Account
              </Button>
            </div>
          ) : (
            <div className="space-y-4 p-4 bg-red-50 dark:bg-red-950/20 rounded-xl border border-red-200 dark:border-red-900">
              <p className="text-sm text-red-800 dark:text-red-300 font-medium">
                Are you sure? This will permanently delete:
              </p>
              <ul className="text-xs text-red-700 dark:text-red-400 space-y-1 ml-4 list-disc">
                <li>Your profile and creator data</li>
                <li>All extracted deals and invoices</li>
                <li>Audit reports and skills map</li>
                <li>Agent action history</li>
              </ul>
              <div>
                <label className="text-xs text-red-700 dark:text-red-400 block mb-1.5">
                  Type <strong>DELETE</strong> to confirm:
                </label>
                <input
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder="DELETE"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-red-300 dark:border-red-800 bg-background focus:outline-none focus:ring-2 focus:ring-red-500"
                  data-testid="delete-confirm-input"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowDeleteConfirm(false);
                    setDeleteConfirmText('');
                  }}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleteConfirmText !== 'DELETE' || deleting}
                  className="bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                  data-testid="confirm-delete-btn"
                >
                  {deleting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                      Permanently Delete
                    </>
                  )}
                </Button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
