"use client";

import { type ExperimentOpportunity } from "@/lib/api";

const RISK_COLORS: Record<string, string> = {
  low: "text-[var(--success)] border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.08)]",
  medium: "text-[var(--warning)] border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.08)]",
  high: "text-[var(--danger)] border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)]",
};

const EFFORT_LABELS: Record<string, string> = {
  low: "Quick win",
  medium: "Moderate effort",
  high: "High effort",
};

interface OpportunityCardProps {
  opportunity: ExperimentOpportunity;
  onFrame?: (hypothesis: string) => void;
}

export function OpportunityCard({ opportunity, onFrame }: OpportunityCardProps) {
  const riskClass = RISK_COLORS[opportunity.risk_level] ?? RISK_COLORS.medium;
  const effortLabel = EFFORT_LABELS[opportunity.effort_level] ?? opportunity.effort_level;
  const impactPct = Math.round(opportunity.expected_impact_score * 100);

  return (
    <div className="surface-panel flex flex-col gap-5 rounded-3xl p-6 transition duration-150 hover:brightness-105">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="metric-mono flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-semibold text-white">
            {opportunity.rank}
          </span>
          <h3 className="text-base font-semibold leading-snug tracking-[-0.02em] text-[var(--text-primary)]">
            {opportunity.title}
          </h3>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium uppercase tracking-[0.12em] ${riskClass}`}
          >
            {opportunity.risk_level} risk
          </span>
          <span className="metric-mono text-xs text-[var(--text-muted)]">{effortLabel}</span>
        </div>
      </div>

      <p className="text-sm leading-7 text-[var(--text-muted)]">{opportunity.hypothesis}</p>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Primary metric
          </p>
          <p className="mt-1 text-sm font-medium text-[var(--text-primary)]">
            {opportunity.primary_metric}
          </p>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Est. lift range
          </p>
          <p className="metric-mono mt-1 text-sm font-semibold text-[var(--text-primary)]">
            +{opportunity.estimated_lift_low_pct.toFixed(0)}%–{opportunity.estimated_lift_high_pct.toFixed(0)}%
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
        <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
          Evidence
        </p>
        <p className="mt-1 text-xs leading-6 text-[var(--text-muted)]">{opportunity.evidence}</p>
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span className="uppercase tracking-[0.12em]">Expected impact</span>
            <span className="metric-mono font-medium text-[var(--text-primary)]">{impactPct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
            <div
              className="h-full rounded-full bg-[var(--primary)]"
              style={{ width: `${impactPct}%` }}
            />
          </div>
        </div>
        {onFrame && (
          <button
            onClick={() => onFrame(opportunity.hypothesis)}
            className="shrink-0 rounded-full border border-[var(--border)] bg-[rgba(99,102,241,0.12)] px-4 py-2 text-xs font-medium text-[var(--primary)] transition duration-150 hover:bg-[rgba(99,102,241,0.22)]"
          >
            Frame experiment
          </button>
        )}
      </div>

      <p className="text-xs text-[var(--text-muted)]">
        <span className="uppercase tracking-[0.12em]">Watch segment: </span>
        {opportunity.segment_to_watch}
      </p>
    </div>
  );
}
