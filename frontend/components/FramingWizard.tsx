"use client";

import { useState } from "react";

import { frameExperiment, type ExperimentDesign } from "@/lib/api";

export function FramingWizard() {
  const [hypothesis, setHypothesis] = useState("");
  const [design, setDesign] = useState<ExperimentDesign | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const result = await frameExperiment(hypothesis);
      setDesign(result);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to frame experiment.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="surface-panel rounded-3xl p-6">
        <div className="mb-5 flex items-center gap-3 text-sm text-[var(--text-muted)]">
          <span className="status-pill bg-[var(--primary)] px-3 py-1 text-white">Step 1</span>
          <span>Describe your hypothesis</span>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <textarea
            value={hypothesis}
            onChange={(event) => setHypothesis(event.target.value)}
            placeholder="Example: If we shorten the checkout form, more mobile users will complete purchase."
            className="min-h-48 w-full rounded-3xl border border-[var(--border)] bg-[rgba(6,8,13,0.92)] px-5 py-4 text-sm leading-7 text-[var(--text-primary)] outline-none transition duration-150 ease-in placeholder:text-[var(--text-muted)] focus:border-[var(--primary)] focus:ring-2 focus:ring-[rgba(99,102,241,0.28)]"
            required
          />
          <div className="flex items-center justify-between">
            <p className="text-sm text-[var(--text-muted)]">
              ExperimentIQ will return a metric recommendation, guardrails, runtime, and tradeoffs.
            </p>
            <button
              type="submit"
              disabled={isLoading}
              className="inline-flex min-w-40 items-center justify-center rounded-full bg-[var(--primary)] px-5 py-3 text-sm font-medium text-white shadow-[0_0_26px_rgba(99,102,241,0.3)] transition duration-150 ease-in hover:-translate-y-0.5 hover:brightness-110 disabled:cursor-not-allowed disabled:translate-y-0 disabled:bg-[rgba(99,102,241,0.45)] disabled:shadow-none"
            >
              {isLoading ? (
                <span className="inline-flex items-center gap-1">
                  <span>Designing</span>
                  <span className="flex gap-1">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white [animation-delay:120ms]" />
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white [animation-delay:240ms]" />
                  </span>
                </span>
              ) : (
                "Generate Design"
              )}
            </button>
          </div>
        </form>
        {error ? <p className="mt-4 text-sm text-[var(--danger)]">{error}</p> : null}
      </section>

      {design ? (
        <section className="surface-panel rounded-3xl p-6">
          <div className="mb-5 flex items-center gap-3 text-sm text-[var(--text-muted)]">
            <span className="status-pill bg-[var(--secondary)] px-3 py-1 text-slate-950">Step 2</span>
            <span>Review the suggested experiment design</span>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Sharpened Hypothesis</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{design.hypothesis}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Primary Metric</h3>
                <p className="metric-mono mt-2 text-sm text-[var(--secondary)]">{design.primary_metric}</p>
                <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">{design.metric_rationale}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Guardrails</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-[var(--text-muted)]">
                  {design.guardrail_metrics.map((metric) => (
                    <li key={metric}>{metric}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Runtime</p>
                  <p className="metric-mono mt-2 text-lg font-semibold text-[var(--text-primary)]">
                    {design.estimated_runtime_days} days
                  </p>
                </div>
                <div className="rounded-2xl border border-[var(--border)] bg-[rgba(255,255,255,0.01)] p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Confidence</p>
                  <p className="metric-mono mt-2 text-lg font-semibold text-[var(--text-primary)]">
                    {(design.confidence * 100).toFixed(0)}%
                  </p>
                </div>
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Unit of Randomization</h3>
                <p className="metric-mono mt-2 text-sm text-[var(--text-muted)]">
                  {design.unit_of_randomization}
                </p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)]">Tradeoffs</h3>
                <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-[var(--text-muted)]">
                  {design.tradeoffs.map((tradeoff) => (
                    <li key={tradeoff}>{tradeoff}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {design.confidence < 0.7 && design.clarifying_questions.length > 0 ? (
            <div className="mt-6 rounded-3xl border border-[rgba(245,158,11,0.28)] bg-[rgba(245,158,11,0.08)] p-5">
              <h3 className="text-sm font-medium text-[var(--warning)]">Clarifying Questions</h3>
              <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-[var(--warning)]">
                {design.clarifying_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
