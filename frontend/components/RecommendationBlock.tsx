import type { Recommendation } from "@/lib/api";

interface RecommendationBlockProps {
  recommendation: Recommendation;
}

const decisionClasses: Record<string, string> = {
  ship: "bg-[rgba(34,197,94,0.12)] text-[var(--success)] border-[rgba(34,197,94,0.26)]",
  iterate: "bg-[rgba(245,158,11,0.12)] text-[var(--warning)] border-[rgba(245,158,11,0.26)]",
  abandon: "bg-[rgba(239,68,68,0.12)] text-[var(--danger)] border-[rgba(239,68,68,0.26)]"
};

export function RecommendationBlock({ recommendation }: RecommendationBlockProps) {
  const decisionClassName =
    decisionClasses[recommendation.decision] ??
    "bg-[rgba(100,116,139,0.16)] text-[var(--text-muted)] border-[var(--border)]";

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
          Recommendation
        </h2>
        <span className={`status-pill border px-4 py-2 text-sm uppercase ${decisionClassName}`}>
          {recommendation.decision}
        </span>
      </div>

      <div className="mt-6 space-y-5 text-sm text-[var(--text-primary)]">
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] px-4 py-4">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Confidence</p>
            <p className="metric-mono text-lg font-semibold text-[var(--text-primary)]">
              {(recommendation.confidence * 100).toFixed(0)}%
            </p>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-[rgba(255,255,255,0.06)]">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--primary)] to-[var(--secondary)]"
              style={{ width: `${Math.max(4, recommendation.confidence * 100)}%` }}
            />
          </div>
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Reasoning</h3>
          <div className="metric-mono mt-2 rounded-2xl border border-[var(--border)] bg-[rgba(6,8,13,0.92)] p-4 text-sm leading-7 text-[var(--text-muted)]">
            {recommendation.reasoning}
          </div>
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Follow-up Cuts</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-[var(--text-muted)]">
            {recommendation.follow_up_cuts.map((cut) => (
              <li key={cut}>{cut}</li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Risks</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-[var(--text-muted)]">
            {recommendation.risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
