"use client";

import { useEffect, useState } from "react";

import { MonitoringPanel } from "@/components/MonitoringPanel";
import { RecommendationBlock } from "@/components/RecommendationBlock";
import {
  getMonitoringReport,
  interpretExperiment,
  type MonitoringReport,
  type Recommendation
} from "@/lib/api";

interface ExperimentDetailPageProps {
  params: {
    id: string;
  };
}

interface ExperimentDetail {
  id: string;
  name: string;
  hypothesis: string;
  status: string;
  trackingKey?: string | null;
}

async function getExperimentDetail(id: string): Promise<ExperimentDetail> {
  const response = await fetch(`/api/experiments/${encodeURIComponent(id)}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include"
  });

  const payload = (await response.json()) as Partial<ExperimentDetail> & { detail?: string };
  if (!response.ok) {
    throw new Error(payload.detail ?? "Failed to load experiment.");
  }

  return {
    id: payload.id ?? id,
    name: payload.name ?? id,
    hypothesis: payload.hypothesis ?? "No hypothesis provided.",
    status: payload.status ?? "unknown",
    trackingKey: payload.trackingKey ?? null
  };
}

export default function ExperimentDetailPage({ params }: ExperimentDetailPageProps) {
  const [experiment, setExperiment] = useState<ExperimentDetail | null>(null);
  const [monitoring, setMonitoring] = useState<MonitoringReport | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const experimentData = await getExperimentDetail(params.id);
        const trackingKey = experimentData.trackingKey || experimentData.id;
        const [monitoringData, recommendationData] = await Promise.all([
          getMonitoringReport(trackingKey),
          interpretExperiment(trackingKey)
        ]);

        setExperiment(experimentData);
        setMonitoring(monitoringData);
        setRecommendation(recommendationData);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load experiment detail.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadData();
  }, [params.id]);

  return (
    <div className="space-y-6">
      <section className="surface-panel rounded-[2rem] p-8 md:p-10">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="space-y-3">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--secondary)]">
              Experiment Detail
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)] md:text-5xl">
              {experiment?.name ?? params.id}
            </h1>
            <p className="metric-mono text-sm text-[var(--text-muted)]">{params.id}</p>
            {experiment?.hypothesis ? (
              <p className="max-w-3xl text-sm leading-7 text-[var(--text-muted)]">
                {experiment.hypothesis}
              </p>
            ) : null}
          </div>

          {experiment?.status ? (
            <span className="status-pill border border-[var(--border)] bg-[rgba(255,255,255,0.03)] px-4 py-2 capitalize text-[var(--text-muted)]">
              {experiment.status}
            </span>
          ) : null}
        </div>
      </section>

      {isLoading ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="surface-panel h-72 animate-pulse rounded-3xl" />
          <div className="surface-panel h-72 animate-pulse rounded-3xl" />
        </div>
      ) : error ? (
        <div className="rounded-3xl border border-[rgba(239,68,68,0.28)] bg-[rgba(239,68,68,0.08)] p-6 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {monitoring ? <MonitoringPanel report={monitoring} /> : null}
          {recommendation ? <RecommendationBlock recommendation={recommendation} /> : null}
        </div>
      )}
    </div>
  );
}
