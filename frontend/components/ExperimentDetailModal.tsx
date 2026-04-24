"use client";

import { useEffect, useState } from "react";

import {
  frameExperiment,
  startExperiment,
  type ExperimentDesign,
  type ExperimentOpportunity,
  type StartExperimentResponse,
} from "@/lib/api";

interface ExperimentDetailModalProps {
  opportunity: ExperimentOpportunity;
  ga4Connected: boolean;
  onClose: () => void;
}

type ModalState = "overview" | "loading_design" | "design" | "starting" | "started" | "error";

const RISK_COLORS: Record<string, string> = {
  low: "text-[var(--success)] border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.08)]",
  medium: "text-[var(--warning)] border-[rgba(251,191,36,0.3)] bg-[rgba(251,191,36,0.08)]",
  high: "text-[var(--danger)] border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)]",
};

export function ExperimentDetailModal({
  opportunity,
  ga4Connected,
  onClose,
}: ExperimentDetailModalProps) {
  const [modalState, setModalState] = useState<ModalState>("overview");
  const [design, setDesign] = useState<ExperimentDesign | null>(null);
  const [started, setStarted] = useState<StartExperimentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  async function handleLoadDesign() {
    setModalState("loading_design");
    setError(null);
    try {
      const result = await frameExperiment(opportunity.hypothesis);
      setDesign(result);
      setModalState("design");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate design.");
      setModalState("error");
    }
  }

  async function handleStartExperiment() {
    if (!design) return;
    setModalState("starting");
    setError(null);
    try {
      const result = await startExperiment({
        name: opportunity.title,
        hypothesis: design.hypothesis,
        description: `Primary metric: ${design.primary_metric}. Est. runtime: ${design.estimated_runtime_days} days.`,
      });
      setStarted(result);
      setModalState("started");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start experiment in GrowthBook.");
      setModalState("error");
    }
  }

  const riskClass = RISK_COLORS[opportunity.risk_level] ?? RISK_COLORS.medium;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      <div
        className="absolute inset-0 bg-[rgba(0,0,0,0.7)] backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative z-10 flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-[var(--border)] bg-[var(--surface)]">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] p-6">
          <div className="flex items-center gap-3">
            <span className="metric-mono flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-semibold text-white">
              {opportunity.rank}
            </span>
            <h2 className="text-base font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
              {opportunity.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
          >
            ✕
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6">
          {modalState === "overview" && (
            <OverviewPanel
              opportunity={opportunity}
              riskClass={riskClass}
              onViewDesign={handleLoadDesign}
            />
          )}

          {modalState === "loading_design" && (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)]" />
              <p className="text-sm text-[var(--text-muted)]">
                Generating structured experiment design…
              </p>
            </div>
          )}

          {modalState === "design" && design && (
            <DesignPanel
              opportunity={opportunity}
              design={design}
              riskClass={riskClass}
              ga4Connected={ga4Connected}
              onStart={handleStartExperiment}
              onBack={() => setModalState("overview")}
            />
          )}

          {modalState === "starting" && (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--secondary)]" />
              <p className="text-sm text-[var(--text-muted)]">
                Creating experiment in GrowthBook…
              </p>
            </div>
          )}

          {modalState === "started" && started && (
            <div className="flex flex-col items-center gap-6 py-8 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[rgba(52,211,153,0.4)] bg-[rgba(52,211,153,0.1)] text-2xl text-[var(--success)]">
                ✓
              </div>
              <div className="space-y-2">
                <p className="font-semibold text-[var(--text-primary)]">
                  Experiment created in GrowthBook
                </p>
                <p className="text-sm text-[var(--text-muted)]">
                  "{started.name}" is ready to configure and launch.
                </p>
              </div>
              <a
                href={started.growthbook_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full bg-[var(--primary)] px-6 py-2.5 text-sm font-medium text-white transition hover:brightness-110"
              >
                Open in GrowthBook →
              </a>
            </div>
          )}

          {modalState === "error" && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-4 text-sm text-[var(--danger)]">
                {error}
              </div>
              <button
                onClick={() => setModalState("overview")}
                className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                ← Back
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function OverviewPanel({
  opportunity,
  riskClass,
  onViewDesign,
}: {
  opportunity: ExperimentOpportunity;
  riskClass: string;
  onViewDesign: () => void;
}) {
  return (
    <div className="space-y-5">
      <p className="text-sm leading-7 text-[var(--text-muted)]">{opportunity.hypothesis}</p>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Primary metric" value={opportunity.primary_metric} />
        <Stat
          label="Est. lift range"
          value={`+${opportunity.estimated_lift_low_pct.toFixed(0)}%–${opportunity.estimated_lift_high_pct.toFixed(0)}%`}
          mono
        />
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
          <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">Risk</p>
          <span className={`mt-1 inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${riskClass}`}>
            {opportunity.risk_level}
          </span>
        </div>
        <Stat label="Effort" value={opportunity.effort_level} />
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
        <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">Evidence</p>
        <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">{opportunity.evidence}</p>
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
        <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">Watch segment</p>
        <p className="mt-1 text-sm text-[var(--text-primary)]">{opportunity.segment_to_watch}</p>
      </div>

      <button
        onClick={onViewDesign}
        className="w-full rounded-full bg-[var(--primary)] py-3 text-sm font-medium text-white shadow-[0_0_20px_rgba(99,102,241,0.25)] transition hover:brightness-110"
      >
        View structured experiment design →
      </button>
    </div>
  );
}

function DesignPanel({
  opportunity,
  design,
  riskClass,
  ga4Connected,
  onStart,
  onBack,
}: {
  opportunity: ExperimentOpportunity;
  design: ExperimentDesign;
  riskClass: string;
  ga4Connected: boolean;
  onStart: () => void;
  onBack: () => void;
}) {
  const confidencePct = Math.round(design.confidence * 100);

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
        ← Overview
      </button>

      <div className="flex items-center gap-3">
        <span className="metric-mono rounded-full border border-[var(--border)] px-3 py-1 text-xs text-[var(--text-muted)]">
          Confidence: {confidencePct}%
        </span>
      </div>

      <p className="text-sm leading-7 text-[var(--text-muted)]">{design.hypothesis}</p>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Primary metric" value={design.primary_metric} />
        <Stat label="Unit of randomization" value={design.unit_of_randomization} />
        <Stat label="Est. runtime" value={`${design.estimated_runtime_days} days`} mono />
        <Stat label="Min. detectable effect" value={`${(design.minimum_detectable_effect * 100).toFixed(1)}%`} mono />
      </div>

      <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
        <p className="mb-2 text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Metric rationale
        </p>
        <p className="text-xs leading-5 text-[var(--text-muted)]">{design.metric_rationale}</p>
      </div>

      {design.guardrail_metrics.length > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
          <p className="mb-2 text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Guardrail metrics
          </p>
          <ul className="space-y-1">
            {design.guardrail_metrics.map((m) => (
              <li key={m} className="text-xs text-[var(--text-muted)]">· {m}</li>
            ))}
          </ul>
        </div>
      )}

      {design.tradeoffs.length > 0 && (
        <div className="rounded-2xl border border-[rgba(251,191,36,0.2)] bg-[rgba(251,191,36,0.05)] px-4 py-3">
          <p className="mb-2 text-xs uppercase tracking-[0.14em] text-[var(--warning)]">Tradeoffs</p>
          <ul className="space-y-1">
            {design.tradeoffs.map((t) => (
              <li key={t} className="text-xs leading-5 text-[var(--text-muted)]">· {t}</li>
            ))}
          </ul>
        </div>
      )}

      {design.clarifying_questions.length > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
          <p className="mb-2 text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Clarifying questions
          </p>
          <ul className="space-y-1">
            {design.clarifying_questions.map((q) => (
              <li key={q} className="text-xs leading-5 text-[var(--text-muted)]">· {q}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="pt-2">
        <button
          onClick={onStart}
          disabled={!ga4Connected}
          title={
            ga4Connected
              ? "Create this experiment in GrowthBook"
              : "Connect an analytics platform to start experiments"
          }
          className="w-full rounded-full bg-[var(--primary)] py-3 text-sm font-medium text-white shadow-[0_0_20px_rgba(99,102,241,0.25)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {ga4Connected
            ? "Start experiment in GrowthBook →"
            : "Connect analytics to start experiment"}
        </button>
        {!ga4Connected && (
          <p className="mt-2 text-center text-xs text-[var(--text-muted)]">
            Analytics platform must be connected to launch experiments.
          </p>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3">
      <p className="text-xs uppercase tracking-[0.14em] text-[var(--text-muted)]">{label}</p>
      <p className={`mt-1 text-sm font-medium text-[var(--text-primary)] ${mono ? "metric-mono" : ""}`}>
        {value}
      </p>
    </div>
  );
}
