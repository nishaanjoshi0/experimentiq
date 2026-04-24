"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ExperimentCard } from "@/components/ExperimentCard";
import { listExperiments, type Experiment } from "@/lib/api";

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setExperiments(await listExperiments());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load experiments.");
      } finally {
        setIsLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <div className="space-y-10">
      <section className="surface-panel relative overflow-hidden rounded-[2rem] p-8 md:p-10">
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(52,211,153,0.12)] via-transparent to-[rgba(99,102,241,0.06)]" />
        <div className="relative flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl space-y-3">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--success)]">
              Evaluate Experiments
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)] md:text-4xl">
              Frame, monitor, and interpret experiments.
            </h1>
            <p className="text-base leading-7 text-[var(--text-muted)]">
              Turn a rough hypothesis into a structured design, watch running experiments
              for data quality issues, and get defensible ship/iterate/abandon recommendations.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-3 md:items-end">
            <Link
              href="/experiments/new"
              className="inline-flex items-center justify-center rounded-full bg-[var(--primary)] px-5 py-3 text-sm font-medium text-white shadow-[0_0_24px_rgba(99,102,241,0.3)] transition hover:-translate-y-0.5 hover:brightness-110"
            >
              New Experiment
            </Link>
            <Link
              href="/select"
              className="text-xs text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
            >
              ← Back to hub
            </Link>
          </div>
        </div>
      </section>

      <section className="space-y-5">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
            Experiment Feed
          </h2>
          {!isLoading && (
            <span className="metric-mono text-sm text-[var(--text-muted)]">
              {experiments.length} total
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="surface-panel h-56 animate-pulse rounded-3xl" />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-6 text-sm text-[var(--danger)]">
            {error}
          </div>
        ) : experiments.length === 0 ? (
          <div className="surface-panel rounded-3xl border border-dashed p-10 text-center">
            <h3 className="text-lg font-medium text-[var(--text-primary)]">No experiments yet</h3>
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              Frame a new hypothesis to get started.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {experiments.map((e) => (
              <ExperimentCard key={e.id} experiment={e} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
