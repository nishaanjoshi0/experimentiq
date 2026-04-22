"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ExperimentCard } from "@/components/ExperimentCard";
import { listExperiments, type Experiment } from "@/lib/api";

export default function HomePage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadExperiments() {
      try {
        const data = await listExperiments();
        setExperiments(data);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load experiments.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadExperiments();
  }, []);

  return (
    <div className="space-y-10">
      <section className="surface-panel relative overflow-hidden rounded-[2rem] p-8 md:p-10">
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(99,102,241,0.16)] via-transparent to-[rgba(34,211,238,0.08)]" />
        <div className="relative flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-3xl space-y-4">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--secondary)]">
            Experimentation Intelligence
          </p>
            <h1 className="max-w-4xl text-4xl font-semibold tracking-[-0.05em] text-[var(--text-primary)] md:text-6xl">
              Make experiment decisions with evidence, not dashboard vibes.
            </h1>
            <p className="max-w-2xl text-base leading-8 text-[var(--text-muted)]">
              ExperimentIQ layers AI judgment on top of GrowthBook so teams can frame stronger
              tests, monitor experiment quality, and act on results with clear, defensible logic.
            </p>
            <div className="flex flex-wrap gap-3 text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">
              <span className="rounded-full border border-[var(--border)] bg-[rgba(17,17,24,0.75)] px-3 py-2">
                SRM Detection
              </span>
              <span className="rounded-full border border-[var(--border)] bg-[rgba(17,17,24,0.75)] px-3 py-2">
                Sequential Testing
              </span>
              <span className="rounded-full border border-[var(--border)] bg-[rgba(17,17,24,0.75)] px-3 py-2">
                AI Recommendations
              </span>
            </div>
          </div>
          <div className="flex flex-col items-start gap-4 md:items-end">
            <Link
              href="/experiments/new"
              className="inline-flex items-center justify-center rounded-full bg-[var(--primary)] px-5 py-3 text-sm font-medium text-white shadow-[0_0_30px_rgba(99,102,241,0.32)] transition duration-150 ease-in hover:-translate-y-0.5 hover:brightness-110"
            >
              New Experiment
            </Link>
            <div className="metric-mono rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.82)] px-4 py-3 text-xs text-[var(--text-muted)]">
              ACTIVE EXPERIMENTS
              <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
                {isLoading ? "--" : experiments.length}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
              Experiment Feed
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Running, draft, and completed experiments from your workspace.
            </p>
          </div>
          {!isLoading && (
            <span className="metric-mono text-sm text-[var(--text-muted)]">{experiments.length} total</span>
          )}
        </div>

        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="surface-panel h-56 animate-pulse rounded-3xl"
              />
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
              Start by framing a new hypothesis and turning it into a structured experiment design.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {experiments.map((experiment) => (
              <ExperimentCard key={experiment.id} experiment={experiment} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
