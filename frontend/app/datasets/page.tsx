"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ExperimentDetailModal } from "@/components/ExperimentDetailModal";
import { OpportunityCard } from "@/components/OpportunityCard";
import {
  analyzeDataset,
  fetchDatasets,
  type DatasetMeta,
  type ExperimentOpportunity,
  type OpportunityReport,
} from "@/lib/api";

type PageState = "select" | "uploading" | "analyzing" | "results" | "error";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetMeta[]>([]);
  const [pageState, setPageState] = useState<PageState>("select");
  const [selectedDataset, setSelectedDataset] = useState<DatasetMeta | null>(null);
  const [csvContent, setCsvContent] = useState("");
  const [report, setReport] = useState<OpportunityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<ExperimentOpportunity | null>(null);
  const [ga4Connected, setGa4Connected] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void fetchDatasets().then(setDatasets).catch(() => {});
    void fetch("/api/auth/status")
      .then((r) => r.json())
      .then((d: { connected?: boolean }) => setGa4Connected(d.connected ?? false))
      .catch(() => {});
  }, []);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPageState("uploading");
    const reader = new FileReader();
    reader.onload = (ev) => {
      setCsvContent((ev.target?.result as string) ?? "");
      setPageState("select");
    };
    reader.readAsText(file);
  }

  async function handleAnalyze(dataset: DatasetMeta, csv: string) {
    setSelectedDataset(dataset);
    setPageState("analyzing");
    setError(null);
    try {
      const result = await analyzeDataset({
        csv_content: csv,
        dataset_type: dataset.id,
      });
      setReport(result);
      setPageState("results");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
      setPageState("error");
    }
  }

  return (
    <div className="space-y-10">
      <header className="surface-panel relative overflow-hidden rounded-[2rem] p-8">
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(99,102,241,0.12)] to-transparent" />
        <div className="relative flex items-end justify-between gap-6">
          <div className="space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--primary)]">
              Dataset Recommendations
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Upload a dataset. Get ranked experiments.
            </h1>
            <p className="max-w-xl text-sm leading-7 text-[var(--text-muted)]">
              Select a pre-built dataset or upload your own GA4-compatible CSV.
              The AI agent analyzes your funnel, segments, and behavioral gaps, then surfaces the
              highest-leverage experiments to run next.
            </p>
          </div>
          <Link href="/select" className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Hub
          </Link>
        </div>
      </header>

      {(pageState === "select" || pageState === "uploading") && (
        <section className="space-y-6">
          <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Choose a dataset
          </h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {datasets.map((ds) => (
              <DatasetCard
                key={ds.id}
                dataset={ds}
                csvContent={csvContent}
                onAnalyze={handleAnalyze}
              />
            ))}
          </div>

          <div className="surface-panel rounded-3xl p-6">
            <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">
              Upload your own CSV
            </h3>
            <p className="mb-4 text-xs leading-5 text-[var(--text-muted)]">
              GA4-compatible format. Columns: device_category, sessions, users, conversions,
              conversion_rate, bounce_rate, revenue.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="rounded-full border border-[var(--border)] px-4 py-2 text-sm text-[var(--text-muted)] transition hover:text-[var(--text-primary)]"
              >
                {csvContent ? "Replace file" : "Choose CSV file"}
              </button>
              {csvContent && (
                <>
                  <span className="text-xs text-[var(--success)]">
                    {csvContent.split("\n").length} rows loaded
                  </span>
                  <button
                    onClick={() =>
                      handleAnalyze(
                        { id: "custom", name: "Custom dataset", description: "", size: "", use_case: "", download_url: "", download_instructions: "", columns_hint: "", industry: "" },
                        csvContent,
                      )
                    }
                    className="rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-medium text-white"
                  >
                    Analyze →
                  </button>
                </>
              )}
            </div>
          </div>
        </section>
      )}

      {pageState === "analyzing" && (
        <section className="surface-panel flex flex-col items-center gap-6 rounded-3xl p-12 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)]" />
          <div className="space-y-2">
            <p className="font-medium text-[var(--text-primary)]">
              Analyzing {selectedDataset?.name}…
            </p>
            <p className="text-sm text-[var(--text-muted)]">
              Ingesting data → RAG retrieval → generating candidates → scoring and ranking
            </p>
          </div>
        </section>
      )}

      {pageState === "error" && (
        <section className="space-y-4">
          <div className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-5 text-sm text-[var(--danger)]">
            {error}
          </div>
          <button onClick={() => setPageState("select")} className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Try again
          </button>
        </section>
      )}

      {pageState === "results" && report && (
        <section className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                {report.opportunities.length} opportunities from {selectedDataset?.name}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{report.analysis_context}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="metric-mono rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-2 text-xs text-[var(--text-muted)]">
                Confidence: {Math.round(report.confidence * 100)}%
              </span>
              <button onClick={() => setPageState("select")} className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                New analysis
              </button>
            </div>
          </div>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {report.opportunities.map((opp) => (
              <OpportunityCard
                key={opp.rank}
                opportunity={opp}
                onFrame={() => setSelectedOpportunity(opp)}
              />
            ))}
          </div>
        </section>
      )}

      {selectedOpportunity && (
        <ExperimentDetailModal
          opportunity={selectedOpportunity}
          ga4Connected={ga4Connected}
          onClose={() => setSelectedOpportunity(null)}
        />
      )}
    </div>
  );
}

function DatasetCard({
  dataset,
  csvContent,
  onAnalyze,
}: {
  dataset: DatasetMeta;
  csvContent: string;
  onAnalyze: (ds: DatasetMeta, csv: string) => void;
}) {
  const [localCsv, setLocalCsv] = useState("");
  const [showInstructions, setShowInstructions] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setLocalCsv((ev.target?.result as string) ?? "");
    reader.readAsText(file);
  }

  return (
    <div className="surface-panel flex flex-col gap-4 rounded-3xl p-5">
      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-[var(--text-muted)]">
          {dataset.industry}
        </p>
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{dataset.name}</h3>
        <p className="text-xs leading-5 text-[var(--text-muted)]">{dataset.description}</p>
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5">{dataset.size}</span>
        <span className="rounded-full border border-[var(--border)] px-2 py-0.5">{dataset.use_case}</span>
      </div>
      <div className="mt-auto flex flex-col gap-2">
        {localCsv ? (
          <button
            onClick={() => onAnalyze(dataset, localCsv)}
            className="rounded-full bg-[var(--primary)] px-4 py-2 text-xs font-medium text-white transition hover:-translate-y-0.5"
          >
            Analyze →
          </button>
        ) : (
          <>
            <input ref={fileRef} type="file" accept=".csv" onChange={handleFile} className="hidden" />
            <button
              onClick={() => fileRef.current?.click()}
              className="rounded-full border border-[var(--primary)] px-4 py-2 text-xs font-medium text-[var(--primary)] transition hover:bg-[rgba(99,102,241,0.1)]"
            >
              Upload CSV
            </button>
            <button
              onClick={() => setShowInstructions(!showInstructions)}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              {showInstructions ? "Hide" : "How to download ↓"}
            </button>
            {showInstructions && (
              <div className="rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] p-3 text-xs leading-5 text-[var(--text-muted)]">
                <p className="mb-2">{dataset.download_instructions}</p>
                <a
                  href={dataset.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--primary)] underline"
                >
                  Open source →
                </a>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
