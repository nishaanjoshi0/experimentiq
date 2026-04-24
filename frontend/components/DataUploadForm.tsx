"use client";

import { useState } from "react";

import { type OpportunityRequest } from "@/lib/api";

interface DataUploadFormProps {
  onSubmit: (request: OpportunityRequest) => void;
  isLoading: boolean;
}

export function DataUploadForm({ onSubmit, isLoading }: DataUploadFormProps) {
  const [dataSource, setDataSource] = useState<"demo" | "csv">("demo");
  const [companyDescription, setCompanyDescription] = useState("");
  const [csvContent, setCsvContent] = useState("");
  const [conversionRate, setConversionRate] = useState("");
  const [ctr, setCtr] = useState("");

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setCsvContent((ev.target?.result as string) ?? "");
    };
    reader.readAsText(file);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const metrics: Record<string, number> = {};
    if (conversionRate) metrics["conversion_rate"] = parseFloat(conversionRate) / 100;
    if (ctr) metrics["ctr"] = parseFloat(ctr) / 100;

    onSubmit({
      company_description: companyDescription,
      current_metrics: metrics,
      data_source: dataSource,
      csv_content: dataSource === "csv" ? csvContent : undefined,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6">
      <div className="grid gap-4 md:grid-cols-2">
        <button
          type="button"
          onClick={() => setDataSource("demo")}
          className={`rounded-2xl border p-5 text-left transition duration-150 ${
            dataSource === "demo"
              ? "border-[var(--primary)] bg-[rgba(99,102,241,0.1)]"
              : "border-[var(--border)] bg-[rgba(10,10,15,0.6)] hover:border-[var(--primary)]"
          }`}
        >
          <p className="text-sm font-semibold text-[var(--text-primary)]">Google Merch Store demo</p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">
            50K sessions · Jan–Mar 2024 · Real GA4-format e-commerce data with mobile/desktop gaps,
            cart abandonment, and funnel drop-offs.
          </p>
        </button>
        <button
          type="button"
          onClick={() => setDataSource("csv")}
          className={`rounded-2xl border p-5 text-left transition duration-150 ${
            dataSource === "csv"
              ? "border-[var(--primary)] bg-[rgba(99,102,241,0.1)]"
              : "border-[var(--border)] bg-[rgba(10,10,15,0.6)] hover:border-[var(--primary)]"
          }`}
        >
          <p className="text-sm font-semibold text-[var(--text-primary)]">Upload your CSV</p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-muted)]">
            GA4 export format. Columns: device_category, sessions, users, conversions,
            conversion_rate, bounce_rate, revenue.
          </p>
        </button>
      </div>

      {dataSource === "csv" && (
        <div className="flex flex-col gap-2">
          <label className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            CSV file
          </label>
          <input
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            className="rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-2.5 text-sm text-[var(--text-muted)] file:mr-3 file:rounded-full file:border-0 file:bg-[var(--primary)] file:px-3 file:py-1 file:text-xs file:text-white"
          />
          {csvContent && (
            <p className="text-xs text-[var(--success)]">
              File loaded — {csvContent.split("\n").length} rows
            </p>
          )}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <label className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
          Company / product description{" "}
          <span className="normal-case tracking-normal">(optional)</span>
        </label>
        <textarea
          value={companyDescription}
          onChange={(e) => setCompanyDescription(e.target.value)}
          placeholder="e.g. B2C e-commerce store selling branded merchandise. Primary audience is 18–35 year-olds. Mobile traffic is growing."
          rows={3}
          className="w-full resize-none rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--primary)] focus:outline-none"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            Current conversion rate %{" "}
            <span className="normal-case tracking-normal">(optional)</span>
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            value={conversionRate}
            onChange={(e) => setConversionRate(e.target.value)}
            placeholder="e.g. 2.4"
            className="rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--primary)] focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-2">
          <label className="text-xs uppercase tracking-[0.16em] text-[var(--text-muted)]">
            CTR %{" "}
            <span className="normal-case tracking-normal">(optional)</span>
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            max="100"
            value={ctr}
            onChange={(e) => setCtr(e.target.value)}
            placeholder="e.g. 15"
            className="rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.6)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--primary)] focus:outline-none"
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading || (dataSource === "csv" && !csvContent)}
        className="inline-flex items-center justify-center gap-2 rounded-full bg-[var(--primary)] px-6 py-3 text-sm font-medium text-white shadow-[0_0_30px_rgba(99,102,241,0.32)] transition duration-150 hover:-translate-y-0.5 hover:brightness-110 disabled:pointer-events-none disabled:opacity-40"
      >
        {isLoading ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Analyzing data…
          </>
        ) : (
          "Discover experiment opportunities"
        )}
      </button>
    </form>
  );
}
