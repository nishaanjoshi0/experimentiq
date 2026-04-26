"use client";

import Link from "next/link";
import { useRef, useState } from "react";

type PageState = "form" | "analyzing" | "results" | "error";

interface StatTest {
  metric: string;
  control_value: number;
  treatment_value: number;
  relative_lift_pct: number;
  p_value: number;
  ci_low_pct: number;
  ci_high_pct: number;
  is_significant: boolean;
}

interface VariantMetrics {
  name: string;
  users: number;
  conversions: number;
  conversion_rate: number;
  revenue_total: number;
  revenue_per_user: number;
  guardrail_rates: Record<string, number>;
}

interface SRMResult {
  passed: boolean;
  chi_square: number;
  p_value: number;
  message: string;
}

interface InterpretResult {
  variants: Record<string, VariantMetrics>;
  srm: SRMResult;
  stat_tests: StatTest[];
  novelty_warning: boolean;
  novelty_message: string;
  verdict: string;
  confidence: number;
  headline: string;
  narrative: string;
  key_evidence: string[];
  risks: string[];
  follow_up: string[];
  data_source: string;
}

const VERDICT_STYLES: Record<string, string> = {
  "ship": "border-[rgba(52,211,153,0.4)] bg-[rgba(52,211,153,0.08)] text-[var(--success)]",
  "don't ship": "border-[rgba(239,68,68,0.4)] bg-[rgba(239,68,68,0.08)] text-[var(--danger)]",
  "run longer": "border-[rgba(251,191,36,0.4)] bg-[rgba(251,191,36,0.08)] text-[var(--warning)]",
};

export default function InterpretPage() {
  const [pageState, setPageState] = useState<PageState>("form");
  const [result, setResult] = useState<InterpretResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const assignmentRef = useRef<HTMLInputElement>(null);
  const eventsRef = useRef<HTMLInputElement>(null);
  const [assignmentFile, setAssignmentFile] = useState<File | null>(null);
  const [eventsFile, setEventsFile] = useState<File | null>(null);
  const [hypothesis, setHypothesis] = useState("");
  const [targetEvent, setTargetEvent] = useState("");
  const [guardrailEvents, setGuardrailEvents] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!assignmentFile || !eventsFile || !hypothesis || !targetEvent) return;

    setPageState("analyzing");
    setError(null);

    const formData = new FormData();
    formData.append("assignment_file", assignmentFile);
    formData.append("events_file", eventsFile);
    formData.append("hypothesis", hypothesis);
    formData.append("target_event", targetEvent);
    formData.append("guardrail_events", guardrailEvents);
    formData.append("start_date", startDate);
    formData.append("end_date", endDate);

    try {
      const res = await fetch("/api/experiments/interpret", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      const data = await res.json() as InterpretResult & { detail?: string };
      if (!res.ok) throw new Error(data.detail ?? "Analysis failed.");
      setResult(data);
      setPageState("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
      setPageState("error");
    }
  }

  const verdictStyle = result ? (VERDICT_STYLES[result.verdict.toLowerCase()] ?? VERDICT_STYLES["run longer"]) : "";

  return (
    <div className="space-y-10">
      <header className="surface-panel relative overflow-hidden rounded-[2rem] p-8">
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(52,211,153,0.10)] to-transparent" />
        <div className="relative flex items-end justify-between gap-6">
          <div className="space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--success)]">
              Post-Experiment Analysis
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Interpret your experiment results.
            </h1>
            <p className="max-w-xl text-sm leading-7 text-[var(--text-muted)]">
              Upload raw assignment and event logs. The AI validates integrity, computes stats,
              and tells the full story — what moved, what didn't, and whether to ship.
            </p>
          </div>
          <Link href="/select" className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Hub
          </Link>
        </div>
      </header>

      {pageState === "form" && (
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* File uploads */}
          <div className="grid gap-4 md:grid-cols-2">
            <FileUploadCard
              label="Assignment data"
              hint="Columns: user_id, variant, timestamp"
              file={assignmentFile}
              inputRef={assignmentRef}
              onChange={setAssignmentFile}
            />
            <FileUploadCard
              label="Event log"
              hint="Columns: user_id, event, value, timestamp"
              file={eventsFile}
              inputRef={eventsRef}
              onChange={setEventsFile}
            />
          </div>

          {/* Metadata */}
          <div className="surface-panel space-y-5 rounded-3xl p-6">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Experiment metadata</h2>

            <div className="space-y-2">
              <label className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                Hypothesis
              </label>
              <textarea
                value={hypothesis}
                onChange={(e) => setHypothesis(e.target.value)}
                placeholder="e.g. Adding a progress bar to checkout will increase purchase completion rate by reducing uncertainty."
                rows={2}
                required
                className="w-full resize-none rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--success)] focus:outline-none"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Target event name
                </label>
                <input
                  type="text"
                  value={targetEvent}
                  onChange={(e) => setTargetEvent(e.target.value)}
                  placeholder="e.g. purchase"
                  required
                  className="w-full rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--success)] focus:outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Guardrail events <span className="normal-case text-[var(--text-muted)]">(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={guardrailEvents}
                  onChange={(e) => setGuardrailEvents(e.target.value)}
                  placeholder="e.g. refund, support_ticket"
                  className="w-full rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:border-[var(--success)] focus:outline-none"
                />
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Start date <span className="normal-case">(optional)</span>
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] focus:border-[var(--success)] focus:outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  End date <span className="normal-case">(optional)</span>
                </label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] focus:border-[var(--success)] focus:outline-none"
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={!assignmentFile || !eventsFile || !hypothesis || !targetEvent}
            className="w-full rounded-full bg-[var(--success)] py-3.5 text-sm font-semibold text-white shadow-[0_0_24px_rgba(52,211,153,0.25)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Analyze experiment →
          </button>
        </form>
      )}

      {pageState === "analyzing" && (
        <section className="surface-panel flex flex-col items-center gap-6 rounded-3xl p-16 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--success)]" />
          <div className="space-y-2">
            <p className="font-medium text-[var(--text-primary)]">Analyzing experiment…</p>
            <p className="text-sm text-[var(--text-muted)]">
              Joining logs → building metrics → SRM check → stats → AI interpretation
            </p>
          </div>
        </section>
      )}

      {pageState === "error" && (
        <section className="space-y-4">
          <div className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-5 text-sm text-[var(--danger)]">
            {error}
          </div>
          <button onClick={() => setPageState("form")} className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Try again
          </button>
        </section>
      )}

      {pageState === "results" && result && (
        <div className="space-y-6">
          {/* Verdict */}
          <div className={`rounded-3xl border p-6 ${verdictStyle}`}>
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-semibold uppercase tracking-[0.2em] opacity-70">Verdict</span>
                  <span className={`rounded-full border px-3 py-0.5 text-sm font-bold uppercase tracking-wide ${verdictStyle}`}>
                    {result.verdict}
                  </span>
                  <span className="metric-mono rounded-full border border-[var(--border)] px-3 py-0.5 text-xs text-[var(--text-muted)]">
                    {Math.round(result.confidence * 100)}% confidence
                  </span>
                </div>
                <p className="text-base font-semibold">{result.headline}</p>
              </div>
              <button
                onClick={() => setPageState("form")}
                className="shrink-0 text-xs opacity-60 hover:opacity-100"
              >
                ← New analysis
              </button>
            </div>
          </div>

          {/* Warnings */}
          {(!result.srm.passed || result.novelty_warning) && (
            <div className="space-y-3">
              {!result.srm.passed && (
                <div className="rounded-2xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] px-4 py-3 text-sm text-[var(--danger)]">
                  ⚠ SRM detected — {result.srm.message}
                </div>
              )}
              {result.novelty_warning && (
                <div className="rounded-2xl border border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.08)] px-4 py-3 text-sm text-[var(--warning)]">
                  ⚠ Novelty effect — {result.novelty_message}
                </div>
              )}
            </div>
          )}

          {/* Stats table */}
          <div className="surface-panel overflow-hidden rounded-3xl">
            <div className="border-b border-[var(--border)] px-6 py-4">
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Statistical results</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs uppercase tracking-[0.12em] text-[var(--text-muted)]">
                    <th className="px-6 py-3">Metric</th>
                    <th className="px-6 py-3">Control</th>
                    <th className="px-6 py-3">Treatment</th>
                    <th className="px-6 py-3">Lift</th>
                    <th className="px-6 py-3">p-value</th>
                    <th className="px-6 py-3">95% CI</th>
                    <th className="px-6 py-3">Sig.</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stat_tests.map((t) => (
                    <tr key={t.metric} className="border-b border-[var(--border)] last:border-0">
                      <td className="px-6 py-3 font-medium text-[var(--text-primary)]">{t.metric}</td>
                      <td className="metric-mono px-6 py-3 text-[var(--text-muted)]">
                        {(t.control_value * 100).toFixed(2)}%
                      </td>
                      <td className="metric-mono px-6 py-3 text-[var(--text-muted)]">
                        {(t.treatment_value * 100).toFixed(2)}%
                      </td>
                      <td className={`metric-mono px-6 py-3 font-semibold ${t.relative_lift_pct >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>
                        {t.relative_lift_pct >= 0 ? "+" : ""}{t.relative_lift_pct.toFixed(1)}%
                      </td>
                      <td className="metric-mono px-6 py-3 text-[var(--text-muted)]">
                        {t.p_value < 0.001 ? "<0.001" : t.p_value.toFixed(3)}
                      </td>
                      <td className="metric-mono px-6 py-3 text-[var(--text-muted)]">
                        [{t.ci_low_pct.toFixed(1)}%, {t.ci_high_pct.toFixed(1)}%]
                      </td>
                      <td className="px-6 py-3">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${t.is_significant ? "bg-[rgba(52,211,153,0.15)] text-[var(--success)]" : "bg-[rgba(255,255,255,0.05)] text-[var(--text-muted)]"}`}>
                          {t.is_significant ? "Yes" : "No"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Variant summary */}
          <div className="grid gap-4 md:grid-cols-2">
            {Object.values(result.variants).map((v) => (
              <div key={v.name} className="surface-panel rounded-3xl p-5 space-y-3">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">{v.name}</p>
                <div className="grid grid-cols-2 gap-3">
                  <MiniStat label="Users" value={v.users.toLocaleString()} />
                  <MiniStat label="Conversions" value={v.conversions.toLocaleString()} />
                  <MiniStat label="CVR" value={`${(v.conversion_rate * 100).toFixed(2)}%`} mono />
                  <MiniStat label="Rev / user" value={`$${v.revenue_per_user.toFixed(2)}`} mono />
                </div>
              </div>
            ))}
          </div>

          {/* Narrative */}
          <div className="surface-panel rounded-3xl p-6 space-y-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">Full interpretation</h2>
            <div className="space-y-3 text-sm leading-7 text-[var(--text-muted)]">
              {result.narrative.split("\n\n").map((para, i) => (
                <p key={i}>{para}</p>
              ))}
            </div>
          </div>

          {/* Evidence + Risks + Follow-up */}
          <div className="grid gap-4 md:grid-cols-3">
            <ListCard title="Key evidence" items={result.key_evidence} color="success" />
            <ListCard title="Risks" items={result.risks} color="danger" />
            <ListCard title="Follow-up" items={result.follow_up} color="primary" />
          </div>
        </div>
      )}
    </div>
  );
}

function FileUploadCard({
  label, hint, file, inputRef, onChange,
}: {
  label: string;
  hint: string;
  file: File | null;
  inputRef: React.RefObject<HTMLInputElement>;
  onChange: (f: File) => void;
}) {
  return (
    <div className="surface-panel flex flex-col gap-3 rounded-3xl p-5">
      <div>
        <p className="text-sm font-semibold text-[var(--text-primary)]">{label}</p>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">{hint}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f); }}
      />
      {file ? (
        <div className="flex items-center gap-2">
          <span className="flex-1 truncate text-xs text-[var(--success)]">{file.name}</span>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            Replace
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="rounded-full border border-[var(--border)] px-4 py-2 text-xs text-[var(--text-muted)] transition hover:border-[var(--success)] hover:text-[var(--success)]"
        >
          Upload CSV
        </button>
      )}
    </div>
  );
}

function MiniStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-3 py-2">
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold text-[var(--text-primary)] ${mono ? "metric-mono" : ""}`}>{value}</p>
    </div>
  );
}

function ListCard({ title, items, color }: { title: string; items: string[]; color: string }) {
  const colorMap: Record<string, string> = {
    success: "text-[var(--success)]",
    danger: "text-[var(--danger)]",
    primary: "text-[var(--primary)]",
  };
  return (
    <div className="surface-panel rounded-3xl p-5 space-y-3">
      <p className={`text-xs font-semibold uppercase tracking-[0.14em] ${colorMap[color]}`}>{title}</p>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="text-xs leading-5 text-[var(--text-muted)]">· {item}</li>
        ))}
      </ul>
    </div>
  );
}
