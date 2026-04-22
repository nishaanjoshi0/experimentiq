import type { MonitoringReport } from "@/lib/api";

interface MonitoringPanelProps {
  report: MonitoringReport;
}

const healthClasses: Record<string, string> = {
  healthy: "bg-[rgba(34,197,94,0.12)] text-[var(--success)] border-[rgba(34,197,94,0.22)]",
  warning: "bg-[rgba(245,158,11,0.12)] text-[var(--warning)] border-[rgba(245,158,11,0.22)]",
  critical: "bg-[rgba(239,68,68,0.12)] text-[var(--danger)] border-[rgba(239,68,68,0.22)]"
};

export function MonitoringPanel({ report }: MonitoringPanelProps) {
  const healthClassName =
    healthClasses[report.health_status] ??
    "bg-[rgba(100,116,139,0.16)] text-[var(--text-muted)] border-[var(--border)]";

  return (
    <section className="surface-panel rounded-3xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
            Monitoring
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">{report.summary}</p>
        </div>
        <span className={`status-pill border capitalize ${healthClassName}`}>
          {report.health_status}
        </span>
      </div>

      <div className="mt-6 space-y-5 text-sm text-[var(--text-primary)]">
        <div>
          <h3 className="font-medium text-[var(--text-primary)]">SRM Check</h3>
          <p className="mt-2 text-[var(--text-muted)]">
            {report.srm_check
              ? report.srm_check.has_srm
                ? `SRM detected (p=${report.srm_check.p_value.toFixed(4)}).`
                : `No SRM detected (p=${report.srm_check.p_value.toFixed(4)}).`
              : "SRM check unavailable."}
          </p>
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Data Quality</h3>
          {report.data_quality ? (
            <ul className="mt-2 space-y-2">
              {Object.entries(report.data_quality.checks).map(([check, passed]) => (
                <li
                  key={check}
                  className="flex items-center justify-between rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] px-4 py-3"
                >
                  <span className="capitalize text-[var(--text-muted)]">{check.replaceAll("_", " ")}</span>
                  <span className={`metric-mono ${passed ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                    {passed ? "● PASS" : "● FAIL"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[var(--text-muted)]">Data quality checks unavailable.</p>
          )}
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Sequential Test</h3>
          <p className="metric-mono mt-2 text-[var(--text-muted)]">
            {report.sequential_test
              ? `Recommendation: ${report.sequential_test.recommendation.replaceAll("_", " ")}`
              : "Sequential test not run."}
          </p>
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Novelty Check</h3>
          {report.novelty_check ? (
            <div className="mt-2 space-y-3">
              <div className="flex items-center justify-between gap-4">
                <p className="text-[var(--text-muted)]">
                  {report.novelty_check.has_novelty
                    ? report.novelty_check.message
                    : "No novelty effect detected."}
                </p>
                {report.novelty_check.has_novelty ? (
                  <span className="status-pill border border-[rgba(245,158,11,0.22)] bg-[rgba(245,158,11,0.12)] text-[var(--warning)]">
                    Warning
                  </span>
                ) : null}
              </div>
              <div className="grid gap-2 md:grid-cols-3">
                <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Early Lift</p>
                  <p className="metric-mono mt-2 text-sm text-[var(--text-primary)]">
                    {report.novelty_check.early_window_lift.toFixed(4)}
                  </p>
                </div>
                <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Overall Lift</p>
                  <p className="metric-mono mt-2 text-sm text-[var(--text-primary)]">
                    {report.novelty_check.overall_lift.toFixed(4)}
                  </p>
                </div>
                <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Novelty Ratio</p>
                  <p className="metric-mono mt-2 text-sm text-[var(--text-primary)]">
                    {report.novelty_check.novelty_ratio.toFixed(2)}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-[var(--text-muted)]">Novelty check not run.</p>
          )}
        </div>

        <div>
          <h3 className="font-medium text-[var(--text-primary)]">Suggested Actions</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-[var(--text-muted)]">
            {report.suggested_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
