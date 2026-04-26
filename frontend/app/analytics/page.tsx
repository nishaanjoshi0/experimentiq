"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ExperimentDetailModal } from "@/components/ExperimentDetailModal";
import { OpportunityCard } from "@/components/OpportunityCard";
import {
  connectGA4,
  disconnectGA4,
  getGA4Recommendations,
  getGA4Status,
  type ConnectionStatus,
  type ExperimentOpportunity,
  type OpportunityReport,
} from "@/lib/api";

type PageState = "loading" | "platform_select" | "connecting" | "connected" | "analyzing" | "results" | "error";

const COMING_SOON_PLATFORMS = [
  { name: "Mixpanel", logo: "M", color: "rgba(99,102,241,0.15)" },
  { name: "Amplitude", logo: "A", color: "rgba(34,211,238,0.1)" },
  { name: "Segment", logo: "S", color: "rgba(52,211,153,0.1)" },
  { name: "PostHog", logo: "P", color: "rgba(251,191,36,0.1)" },
];

export default function AnalyticsPage() {
  const [pageState, setPageState] = useState<PageState>("loading");
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [report, setReport] = useState<OpportunityReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<ExperimentOpportunity | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const errorParam = params.get("error");

    if (errorParam) {
      const messages: Record<string, string> = {
        oauth_failed: "Google OAuth failed — token exchange was rejected. Check your OAuth credentials.",
        no_code: "No authorization code received from Google.",
        callback_timeout: "Connection timed out while exchanging tokens with Google. Try again.",
      };
      setError(messages[errorParam] ?? `OAuth error: ${errorParam}`);
      setPageState("error");
      window.history.replaceState({}, "", "/analytics");
      return;
    }

    if (params.get("connected") === "true") {
      window.history.replaceState({}, "", "/analytics");
    }

    void getGA4Status()
      .then((s) => {
        setStatus(s);
        setPageState(s.connected ? "connected" : "platform_select");
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to check GA4 connection status.");
        setPageState("error");
      });
  }, []);

  async function handleConnectGA4() {
    setPageState("connecting");
    try {
      const { auth_url } = await connectGA4();
      window.location.href = auth_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to initiate OAuth.");
      setPageState("error");
    }
  }

  async function handleDisconnect() {
    await disconnectGA4().catch(() => {});
    setStatus(null);
    setReport(null);
    setPageState("platform_select");
  }

  async function handleGetRecommendations() {
    setPageState("analyzing");
    setError(null);
    try {
      const result = await getGA4Recommendations({});
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
        <div className="absolute inset-0 bg-gradient-to-br from-[rgba(34,211,238,0.10)] to-transparent" />
        <div className="relative flex items-end justify-between gap-6">
          <div className="space-y-2">
            <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--secondary)]">
              Analytics Integration
            </p>
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Connect your analytics platform.
            </h1>
            <p className="max-w-xl text-sm leading-7 text-[var(--text-muted)]">
              Connect GA4 and get experiment recommendations grounded in your live funnel data,
              device segments, and real conversion gaps.
            </p>
          </div>
          <Link href="/select" className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Hub
          </Link>
        </div>
      </header>

      {pageState === "loading" && (
        <section className="surface-panel flex items-center justify-center rounded-3xl p-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--secondary)]" />
        </section>
      )}

      {(pageState === "platform_select" || pageState === "connecting") && (
        <section className="space-y-6">
          <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
            Choose a platform
          </h2>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <button
              onClick={handleConnectGA4}
              disabled={pageState === "connecting"}
              className="surface-panel group flex flex-col items-start gap-4 rounded-3xl border border-[rgba(34,211,238,0.3)] p-6 text-left transition hover:border-[rgba(34,211,238,0.6)] hover:brightness-110 disabled:pointer-events-none disabled:opacity-60"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[rgba(34,211,238,0.12)] text-base font-bold text-[var(--secondary)]">
                G4
              </div>
              <div>
                <p className="font-semibold text-[var(--text-primary)]">Google Analytics 4</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {pageState === "connecting" ? "Redirecting to Google…" : "Connect via OAuth"}
                </p>
              </div>
              <span className="rounded-full border border-[rgba(34,211,238,0.4)] px-2.5 py-0.5 text-xs font-medium text-[var(--secondary)]">
                Active
              </span>
            </button>

            {COMING_SOON_PLATFORMS.map((p) => (
              <div
                key={p.name}
                className="surface-panel flex flex-col items-start gap-4 rounded-3xl border border-[var(--border)] p-6 opacity-50"
              >
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-base font-bold text-[var(--text-muted)]"
                  style={{ background: p.color }}
                >
                  {p.logo}
                </div>
                <div>
                  <p className="font-semibold text-[var(--text-primary)]">{p.name}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">Not yet available</p>
                </div>
                <span className="rounded-full border border-[var(--border)] px-2.5 py-0.5 text-xs text-[var(--text-muted)]">
                  Coming soon
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {pageState === "connected" && status && (
        <section className="space-y-6">
          <div className="surface-panel rounded-3xl border border-[rgba(34,211,238,0.3)] p-6">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[rgba(34,211,238,0.12)] text-base font-bold text-[var(--secondary)]">
                  G4
                </div>
                <div>
                  <p className="font-semibold text-[var(--text-primary)]">Google Analytics 4 — Connected</p>
                  <p className="text-xs text-[var(--text-muted)]">
                    {status.email} · Property {status.property_id}
                  </p>
                </div>
                <span className="rounded-full border border-[rgba(52,211,153,0.4)] bg-[rgba(52,211,153,0.08)] px-2.5 py-1 text-xs font-medium text-[var(--success)]">
                  Live
                </span>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleGetRecommendations}
                  className="rounded-full bg-[var(--primary)] px-5 py-2.5 text-sm font-medium text-white shadow-[0_0_20px_rgba(99,102,241,0.3)] transition hover:-translate-y-0.5"
                >
                  Generate recommendations
                </button>
                <button
                  onClick={handleDisconnect}
                  className="rounded-full border border-[var(--border)] px-4 py-2.5 text-sm text-[var(--text-muted)] transition hover:text-[var(--danger)]"
                >
                  Disconnect
                </button>
              </div>
            </div>
          </div>
        </section>
      )}

      {pageState === "analyzing" && (
        <section className="surface-panel flex flex-col items-center gap-6 rounded-3xl p-12 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--secondary)]" />
          <div className="space-y-2">
            <p className="font-medium text-[var(--text-primary)]">Pulling live GA4 data…</p>
            <p className="text-sm text-[var(--text-muted)]">
              Fetching device and source segments → funnel analysis → generating ranked opportunities
            </p>
          </div>
        </section>
      )}

      {pageState === "error" && (
        <section className="space-y-4">
          <div className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-5 text-sm text-[var(--danger)]">
            {error}
          </div>
          <button onClick={() => setPageState("platform_select")} className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Try again
          </button>
        </section>
      )}

      {pageState === "results" && report && (
        <section className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                {report.opportunities.length} opportunities from your GA4 data
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{report.analysis_context}</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="metric-mono rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-2 text-xs text-[var(--text-muted)]">
                Confidence: {Math.round(report.confidence * 100)}%
              </span>
              <button onClick={() => setPageState("connected")} className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                Refresh
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
          ga4Connected={!!status?.connected}
          onClose={() => setSelectedOpportunity(null)}
        />
      )}
    </div>
  );
}
