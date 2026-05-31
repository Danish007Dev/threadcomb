'use client'

interface FirstSignalData {
  title: string
  message: string
  detail: string
  sub_detail: string
  deal_count: number
}

interface FirstSignalCardProps {
  signal: FirstSignalData | null
}

export function FirstSignalCard({ signal }: FirstSignalCardProps) {
  if (!signal) return null

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900 p-5 mb-4 animate-in fade-in slide-in-from-bottom-2 duration-500">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span className="text-white text-sm font-bold">{signal.deal_count}</span>
        </div>
        <div className="flex-1">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 mb-1">
            First finding
          </p>
          <p className="text-sm font-medium text-foreground mb-1">{signal.message}</p>
          <p className="text-sm text-muted-foreground mb-0.5">{signal.detail}</p>
          <p className="text-xs text-muted-foreground">{signal.sub_detail}</p>
        </div>
      </div>
    </div>
  )
}
