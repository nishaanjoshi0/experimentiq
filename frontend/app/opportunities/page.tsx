"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataUploadForm } from "@/components/DataUploadForm";
import { OpportunityCard } from "@/components/OpportunityCard";
import {
  discoverOpportunities,
  type ExperimentOpportunity,
  type OpportunityReport,
  type OpportunityRequest,
} from "@/lib/api";

type PageState = "form" | "loading" | "results" | "error";

export default function OpportunitiesPage() {
  const router = useRouter();
  const [pageState, setPageState] = useState<PageState>("form");
  const [report, setReport] = useState<OpportunityReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(request: OpportunityRequest) {
    setPageState("loading");
    setError(null);
    try {
      const result = await discoverOpportunities(request);
      setReport(result);
      setPageState("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setPageState("error");
    }
  }

  function handleFrameExperiment(hypothesis: string) {
    const params = new URLSearchParams({ hypothesis });
    router.push(`/experiments/new?${params.toString()}`);
  }

  function handleReset() {
    setReport(null);
    setError(null);
    setPageState("form");
  }

  return (
    <div className="space-y-10">
      <section className="surface-panel relative overflow-hidden rounded-[2rem] p-8 md:p-10">
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(34,211,238,0.12)] via-transparent to-[rgba(99,102,241,0.08)]" />
        <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl space-y-3">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--secondary)]">
              Opportunity Discovery
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)] md:text-4xl">
              What should your team test next?
            </h1>
            <p className="text-base leading-7 text-[var(--text-muted)]">
              Connect your analytics data and get a ranked list of experiment opportunities
              grounded in your actual funnel, segments, and behavioral gaps — not generic
              best practices.
            </p>
          </div>
          <Link
            href="/"
            className="shrink-0 rounded-full border border-[var(--border)] px-4 py-2 text-sm text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
          >
            ← Dashboard
          </Link>
        </div>
      </section>

      {pageState === "form" && (
        <section className="surface-panel rounded-3xl p-6 md:p-8">
          <h2 className="mb-6 text-lg font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Configure data source
          </h2>
          <DataUploadForm onSubmit={handleSubmit} isLoading={false} />
        </section>
      )}

      {pageState === "loading" && (
        <section className="surface-panel flex flex-col items-center gap-6 rounded-3xl p-12 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)]" />
          <div className="space-y-2">
            <p className="text-base font-medium text-[var(--text-primary)]">
              Analyzing your data…
            </p>
            <p className="text-sm text-[var(--text-muted)]">
              The agent is ingesting your analytics, running funnel analysis, retrieving relevant
              context, and generating ranked opportunities. This takes 30–60 seconds.
            </p>
          </div>
          <div className="metric-mono flex gap-6 text-xs text-[var(--text-muted)]">
            <span>Ingesting data</span>
            <span>→</span>
            <span>RAG retrieval</span>
            <span>→</span>
            <span>Generating candidates</span>
            <span>→</span>
            <span>Scoring &amp; ranking</span>
          </div>
        </section>
      )}

      {pageState === "error" && (
        <section className="space-y-4">
          <div className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-6 text-sm text-[var(--danger)]">
            {error}
          </div>
          <button
            onClick={handleReset}
            className="rounded-full border border-[var(--border)] px-4 py-2 text-sm text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
          >
            Try again
          </button>
        </section>
      )}

      {pageState === "results" && report && (
        <section className="space-y-8">
          <ResultsHeader report={report} onReset={handleReset} />
          <DataSummaryPanel report={report} />
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {report.opportunities.map((opp: ExperimentOpportunity) => (
              <OpportunityCard
                key={opp.rank}
                opportunity={opp}
                onFrame={handleFrameExperiment}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ResultsHeader({
  report,
  onReset,
}: {
  report: OpportunityReport;
  onReset: () => void;
}) {
  const confidencePct = Math.round(report.confidence * 100);
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="space-y-2">
        <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
          {report.opportunities.length} experiment opportunities found
        </h2>
        <p className="max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
          {report.analysis_context}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-4">
        <div className="metric-mono rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.82)] px-4 py-3 text-xs text-[var(--text-muted)]">
          CONFIDENCE
          <div className="mt-1 text-xl font-semibold text-[var(--text-primary)]">
            {confidencePct}%
          </div>
        </div>
        <button
          onClick={onReset}
          className="rounded-full border border-[var(--border)] px-4 py-2 text-sm text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
        >
          New analysis
        </button>
      </div>
    </div>
  );
}

function DataSummaryPanel({ report }: { report: OpportunityReport }) {
  const s = report.data_summary;
  if (!s || Object.keys(s).length === 0) return null;

  const crPct =
    typeof s.overall_conversion_rate === "number"
      ? (s.overall_conversion_rate * 100).toFixed(1) + "%"
      : null;

  return (
    <div className="surface-panel rounded-3xl p-6">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
        Data snapshot
      </h3>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {s.total_sessions && (
          <Stat label="Sessions" value={Number(s.total_sessions).toLocaleString()} />
        )}
        {crPct && <Stat label="Overall CVR" value={crPct} />}
        {s.total_revenue && (
          <Stat
            label="Revenue"
            value={`$${Number(s.total_revenue).toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
          />
        )}
        {s.date_range && <Stat label="Period" value={String(s.date_range)} />}
      </div>
      {Array.isArray(s.top_insights) && s.top_insights.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Top insights
          </p>
          {(s.top_insights as string[]).map((insight, i) => (
            <p key={i} className="text-xs leading-5 text-[var(--text-muted)]">
              · {insight}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
      <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</p>
      <p className="metric-mono mt-1 text-base font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
