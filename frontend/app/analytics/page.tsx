"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ExperimentDetailModal } from "@/components/ExperimentDetailModal";
import { OpportunityCard } from "@/components/OpportunityCard";
import {
  connectAmplitude,
  connectGA4,
  connectMixpanel,
  connectLaunchDarkly,
  connectStatsig,
  disconnectAmplitude,
  disconnectGA4,
  disconnectMixpanel,
  getAllPlatformStatuses,
  getAmplitudeRecommendations,
  getGA4Recommendations,
  getMixpanelRecommendations,
  getGA4Status,
  getExperimentPlatformStatuses,
  type AllPlatformStatus,
  type AllExperimentPlatformStatus,
  type ConnectionStatus,
  type ExperimentOpportunity,
  type OpportunityReport,
} from "@/lib/api";

type ActivePlatform = "ga4" | "amplitude" | "mixpanel" | null;

interface PlatformDef {
  id: ActivePlatform;
  name: string;
  logo: string;
  color: string;
  borderColor: string;
  description: string;
  authType: "oauth" | "apikey";
  fields: { key: string; label: string; placeholder: string; type?: string }[];
  status: "active" | "soon";
}

const PLATFORMS: PlatformDef[] = [
  {
    id: "ga4",
    name: "Google Analytics 4",
    logo: "G4",
    color: "rgba(34,211,238,0.12)",
    borderColor: "rgba(34,211,238,0.4)",
    description: "Connect via OAuth",
    authType: "oauth",
    fields: [],
    status: "active",
  },
  {
    id: "amplitude",
    name: "Amplitude",
    logo: "A",
    color: "rgba(99,102,241,0.12)",
    borderColor: "rgba(99,102,241,0.4)",
    description: "API Key + Secret Key",
    authType: "apikey",
    fields: [
      { key: "api_key", label: "API Key", placeholder: "Your Amplitude API Key" },
      { key: "api_secret", label: "Secret Key", placeholder: "Your Amplitude Secret Key", type: "password" },
    ],
    status: "active",
  },
  {
    id: "mixpanel",
    name: "Mixpanel",
    logo: "M",
    color: "rgba(239,68,68,0.10)",
    borderColor: "rgba(239,68,68,0.35)",
    description: "Service Account credentials",
    authType: "apikey",
    fields: [
      { key: "username", label: "Service Account Username", placeholder: "service-account@..." },
      { key: "secret", label: "Service Account Secret", placeholder: "Your secret", type: "password" },
      { key: "project_id", label: "Project ID (optional)", placeholder: "1234567" },
    ],
    status: "active",
  },
  {
    id: null,
    name: "Segment",
    logo: "S",
    color: "rgba(52,211,153,0.1)",
    borderColor: "rgba(52,211,153,0.2)",
    description: "Not yet available",
    authType: "apikey",
    fields: [],
    status: "soon",
  },
  {
    id: null,
    name: "PostHog",
    logo: "P",
    color: "rgba(251,191,36,0.1)",
    borderColor: "rgba(251,191,36,0.2)",
    description: "Not yet available",
    authType: "apikey",
    fields: [],
    status: "soon",
  },
];

export default function AnalyticsPage() {
  const [statuses, setStatuses] = useState<AllPlatformStatus | null>(null);
  const [ga4Status, setGa4Status] = useState<ConnectionStatus | null>(null);
  const [expPlatformStatuses, setExpPlatformStatuses] = useState<AllExperimentPlatformStatus | null>(null);
  const [pendingAnalyzeId, setPendingAnalyzeId] = useState<ActivePlatform>(null);
  const [showExpSetup, setShowExpSetup] = useState(false);
  const [expConnecting, setExpConnecting] = useState<"launchdarkly" | "statsig" | null>(null);
  const [expFormValues, setExpFormValues] = useState<Record<string, string>>({});
  const [expConnectError, setExpConnectError] = useState<string | null>(null);
  const [expandedExpPlatform, setExpandedExpPlatform] = useState<"launchdarkly" | "statsig" | null>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<ActivePlatform>(null);
  const [connectingPlatform, setConnectingPlatform] = useState<ActivePlatform>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [activePlatform, setActivePlatform] = useState<ActivePlatform>(null);
  const [report, setReport] = useState<OpportunityReport | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<ExperimentOpportunity | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected") === "true") {
      window.history.replaceState({}, "", "/analytics");
    }

    void Promise.all([
      getAllPlatformStatuses(),
      getGA4Status().catch(() => ({ connected: false } as ConnectionStatus)),
      getExperimentPlatformStatuses().catch(() => null),
    ]).then(([all, ga4, expStatuses]) => {
      setStatuses(all);
      setGa4Status(ga4);
      setExpPlatformStatuses(expStatuses);
    });
  }, []);

  function isConnected(id: ActivePlatform): boolean {
    if (!statuses || !id) return false;
    if (id === "ga4") return ga4Status?.connected ?? false;
    return statuses[id as keyof AllPlatformStatus]?.connected ?? false;
  }

  async function handleConnect() {
    if (!selectedPlatform) return;
    setConnectingPlatform(selectedPlatform);
    setError(null);
    try {
      if (selectedPlatform === "ga4") {
        const { auth_url } = await connectGA4();
        window.location.href = auth_url;
        return;
      }
      if (selectedPlatform === "amplitude") {
        await connectAmplitude(formValues.api_key ?? "", formValues.api_secret ?? "");
      } else if (selectedPlatform === "mixpanel") {
        await connectMixpanel(formValues.username ?? "", formValues.secret ?? "", formValues.project_id);
      }
      const [all, ga4] = await Promise.all([getAllPlatformStatuses(), getGA4Status().catch(() => ({ connected: false } as ConnectionStatus))]);
      setStatuses(all);
      setGa4Status(ga4);
      setSelectedPlatform(null);
      setFormValues({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connection failed. Check your credentials.");
    } finally {
      setConnectingPlatform(null);
    }
  }

  async function handleDisconnect(id: ActivePlatform) {
    if (!id) return;
    if (id === "ga4") await disconnectGA4().catch(() => {});
    else if (id === "amplitude") await disconnectAmplitude();
    else if (id === "mixpanel") await disconnectMixpanel();

    const [all, ga4] = await Promise.all([getAllPlatformStatuses(), getGA4Status().catch(() => ({ connected: false } as ConnectionStatus))]);
    setStatuses(all);
    setGa4Status(ga4);
    if (activePlatform === id) { setActivePlatform(null); setReport(null); }
  }

  function handleAnalyzeClick(id: ActivePlatform) {
    setPendingAnalyzeId(id);
    setShowExpSetup(true);
    setExpConnectError(null);
    setExpFormValues({});
    setExpandedExpPlatform(null);
  }

  async function handleGetRecommendations(id: ActivePlatform) {
    if (!id) return;
    setShowExpSetup(false);
    setActivePlatform(id);
    setIsAnalyzing(true);
    setReport(null);
    setError(null);
    try {
      let result: OpportunityReport;
      if (id === "ga4") result = await getGA4Recommendations({});
      else if (id === "amplitude") result = await getAmplitudeRecommendations({});
      else result = await getMixpanelRecommendations({});
      setReport(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleExpPlatformConnect(platform: "launchdarkly" | "statsig") {
    setExpConnecting(platform);
    setExpConnectError(null);
    try {
      if (platform === "launchdarkly") {
        await connectLaunchDarkly(
          expFormValues.access_token ?? "",
          expFormValues.project_key ?? "default",
          expFormValues.environment_key ?? "test"
        );
      } else {
        await connectStatsig(expFormValues.server_secret ?? "");
      }
      const updated = await getExperimentPlatformStatuses();
      setExpPlatformStatuses(updated);
      setExpandedExpPlatform(null);
      setExpFormValues({});
    } catch (e) {
      setExpConnectError(e instanceof Error ? e.message : "Connection failed.");
    } finally {
      setExpConnecting(null);
    }
  }

  function isExpConnected(platform: "growthbook" | "launchdarkly" | "statsig"): boolean {
    if (platform === "growthbook") return true;
    return expPlatformStatuses?.[platform]?.connected ?? false;
  }

  const platformDef = selectedPlatform ? PLATFORMS.find((p) => p.id === selectedPlatform) : null;

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
              Connect GA4, Amplitude, or Mixpanel and get experiment recommendations grounded in your live funnel data.
            </p>
          </div>
          <Link href="/select" className="shrink-0 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            ← Hub
          </Link>
        </div>
      </header>

      {/* Platform grid */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--text-primary)]">Choose a platform</h2>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {PLATFORMS.map((p) => {
            const connected = isConnected(p.id);
            const isSoon = p.status === "soon";
            return (
              <div
                key={p.name}
                onClick={() => { if (!isSoon && p.id) setSelectedPlatform(p.id); }}
                className={`surface-panel flex flex-col items-start gap-4 rounded-3xl border p-6 transition ${
                  isSoon
                    ? "opacity-40 cursor-not-allowed"
                    : "cursor-pointer hover:brightness-110"
                }`}
                style={{ borderColor: connected ? p.borderColor : "var(--border)" }}
              >
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-base font-bold"
                  style={{ background: p.color, color: connected ? "var(--text-primary)" : "var(--text-muted)" }}
                >
                  {p.logo}
                </div>
                <div className="flex-1">
                  <p className="font-semibold text-[var(--text-primary)]">{p.name}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">{p.description}</p>
                </div>
                <span
                  className="rounded-full border px-2.5 py-0.5 text-xs font-medium"
                  style={
                    connected
                      ? { borderColor: "rgba(52,211,153,0.4)", color: "var(--success)", background: "rgba(52,211,153,0.08)" }
                      : isSoon
                      ? { borderColor: "var(--border)", color: "var(--text-muted)" }
                      : { borderColor: p.borderColor, color: "var(--text-muted)" }
                  }
                >
                  {connected ? "Connected" : isSoon ? "Coming soon" : "Connect"}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Connection modal */}
      {selectedPlatform && platformDef && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => { setSelectedPlatform(null); setError(null); }}>
          <div className="surface-panel w-full max-w-md rounded-3xl border border-[var(--border)] p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-xl font-semibold text-[var(--text-primary)]">
                Connect {platformDef.name}
              </h3>
              <button onClick={() => { setSelectedPlatform(null); setError(null); }} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">✕</button>
            </div>

            {isConnected(selectedPlatform) ? (
              <div className="space-y-4">
                <p className="text-sm text-[var(--success)]">✓ {platformDef.name} is connected.</p>
                <div className="flex gap-3">
                  <button
                    onClick={() => { setSelectedPlatform(null); handleAnalyzeClick(selectedPlatform); }}
                    className="flex-1 rounded-full bg-[var(--primary)] py-2.5 text-sm font-medium text-white"
                  >
                    Generate recommendations
                  </button>
                  <button
                    onClick={() => { handleDisconnect(selectedPlatform); setSelectedPlatform(null); }}
                    className="rounded-full border border-[var(--border)] px-4 py-2.5 text-sm text-[var(--text-muted)] hover:text-[var(--danger)]"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ) : platformDef.authType === "oauth" ? (
              <div className="space-y-4">
                <p className="text-sm text-[var(--text-muted)]">You'll be redirected to Google to authorize access to your GA4 property.</p>
                <button
                  onClick={handleConnect}
                  disabled={connectingPlatform === selectedPlatform}
                  className="w-full rounded-full bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-60"
                >
                  {connectingPlatform === selectedPlatform ? "Redirecting…" : "Continue with Google →"}
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {platformDef.fields.map((f) => (
                  <div key={f.key} className="space-y-1.5">
                    <label className="text-xs font-medium text-[var(--text-muted)]">{f.label}</label>
                    <input
                      type={f.type ?? "text"}
                      placeholder={f.placeholder}
                      value={formValues[f.key] ?? ""}
                      onChange={(e) => setFormValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                      className="w-full rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--primary)]"
                    />
                  </div>
                ))}
                {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
                <button
                  onClick={handleConnect}
                  disabled={connectingPlatform === selectedPlatform}
                  className="w-full rounded-full bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-60"
                >
                  {connectingPlatform === selectedPlatform ? "Connecting…" : `Connect ${platformDef.name}`}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Connected platforms — quick actions */}
      {(isConnected("ga4") || isConnected("amplitude") || isConnected("mixpanel")) && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold tracking-[-0.02em] text-[var(--text-primary)]">Connected platforms</h2>
          <div className="flex flex-wrap gap-3">
            {(["ga4", "amplitude", "mixpanel"] as ActivePlatform[]).filter(isConnected).map((id) => {
              const def = PLATFORMS.find((p) => p.id === id)!;
              return (
                <button
                  key={id}
                  onClick={() => handleAnalyzeClick(id)}
                  className="flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition hover:-translate-y-0.5"
                  style={{ borderColor: def.borderColor, color: "var(--text-primary)" }}
                >
                  <span style={{ color: "var(--success)" }}>●</span>
                  {def.name} — Analyze
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Analyzing */}
      {isAnalyzing && (
        <section className="surface-panel flex flex-col items-center gap-6 rounded-3xl p-12 text-center">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--secondary)]" />
          <div className="space-y-2">
            <p className="font-medium text-[var(--text-primary)]">
              Pulling live data from {PLATFORMS.find((p) => p.id === activePlatform)?.name}…
            </p>
            <p className="text-sm text-[var(--text-muted)]">
              Fetching segments → funnel analysis → generating ranked opportunities
            </p>
          </div>
        </section>
      )}

      {/* Error */}
      {error && !selectedPlatform && (
        <section className="rounded-3xl border border-[rgba(239,68,68,0.3)] bg-[rgba(239,68,68,0.08)] p-5 text-sm text-[var(--danger)]">
          {error}
        </section>
      )}

      {/* Results */}
      {report && !isAnalyzing && (
        <section className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                {report.opportunities.length} opportunities from {PLATFORMS.find((p) => p.id === activePlatform)?.name}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{report.analysis_context}</p>
            </div>
            <span className="metric-mono rounded-2xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-2 text-xs text-[var(--text-muted)]">
              Confidence: {Math.round(report.confidence * 100)}%
            </span>
          </div>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {report.opportunities.map((opp) => (
              <OpportunityCard key={opp.rank} opportunity={opp} onFrame={() => setSelectedOpportunity(opp)} />
            ))}
          </div>
        </section>
      )}

      {selectedOpportunity && (
        <ExperimentDetailModal
          opportunity={selectedOpportunity}
          ga4Connected={isConnected("ga4")}
          connectedPlatforms={{
            growthbook: true,
            launchdarkly: expPlatformStatuses?.launchdarkly?.connected ?? false,
            statsig: expPlatformStatuses?.statsig?.connected ?? false,
          }}
          onClose={() => setSelectedOpportunity(null)}
        />
      )}

      {/* Experiment platform setup interstitial */}
      {showExpSetup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={() => setShowExpSetup(false)}>
          <div className="surface-panel w-full max-w-lg rounded-3xl border border-[var(--border)] p-8 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                Where do you want to run experiments?
              </h3>
              <button onClick={() => setShowExpSetup(false)} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">✕</button>
            </div>
            <p className="mb-6 text-sm text-[var(--text-muted)]">
              Connect at least one platform. You can always add more later.
            </p>

            <div className="space-y-3">
              {/* GrowthBook — always connected */}
              <div className="flex items-center justify-between rounded-2xl border border-[rgba(52,211,153,0.3)] bg-[rgba(52,211,153,0.06)] px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[rgba(52,211,153,0.15)] text-xs font-bold text-[var(--success)]">GB</span>
                  <div>
                    <p className="text-sm font-medium text-[var(--text-primary)]">GrowthBook</p>
                    <p className="text-xs text-[var(--text-muted)]">Self-hosted · Always available</p>
                  </div>
                </div>
                <span className="text-xs font-medium text-[var(--success)]">✓ Connected</span>
              </div>

              {/* LaunchDarkly */}
              <div className="rounded-2xl border border-[var(--border)] overflow-hidden">
                <div
                  className="flex cursor-pointer items-center justify-between px-4 py-3 hover:bg-[rgba(255,255,255,0.02)]"
                  onClick={() => {
                    if (isExpConnected("launchdarkly")) return;
                    setExpandedExpPlatform(expandedExpPlatform === "launchdarkly" ? null : "launchdarkly");
                    setExpConnectError(null);
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-xl text-xs font-bold text-white" style={{ background: "#405BFF" }}>LD</span>
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">LaunchDarkly</p>
                      <p className="text-xs text-[var(--text-muted)]">Access Token + Project Key</p>
                    </div>
                  </div>
                  {isExpConnected("launchdarkly") ? (
                    <span className="text-xs font-medium text-[var(--success)]">✓ Connected</span>
                  ) : (
                    <span className="text-xs text-[var(--primary)]">{expandedExpPlatform === "launchdarkly" ? "▲ Cancel" : "Connect →"}</span>
                  )}
                </div>
                {expandedExpPlatform === "launchdarkly" && !isExpConnected("launchdarkly") && (
                  <div className="border-t border-[var(--border)] px-4 pb-4 pt-3 space-y-3">
                    {[
                      { key: "access_token", label: "Access Token", placeholder: "api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", type: "password" },
                      { key: "project_key", label: "Project Key", placeholder: "default" },
                      { key: "environment_key", label: "Environment Key", placeholder: "test" },
                    ].map((f) => (
                      <div key={f.key} className="space-y-1">
                        <label className="text-xs font-medium text-[var(--text-muted)]">{f.label}</label>
                        <input
                          type={f.type ?? "text"}
                          placeholder={f.placeholder}
                          value={expFormValues[f.key] ?? ""}
                          onChange={(e) => setExpFormValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                          className="w-full rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[#405BFF]"
                        />
                      </div>
                    ))}
                    <p className="text-xs text-[var(--text-muted)]">Find your token in LaunchDarkly → Settings → Authorization → Access Tokens</p>
                    {expConnectError && <p className="text-xs text-[var(--danger)]">{expConnectError}</p>}
                    <button
                      onClick={() => handleExpPlatformConnect("launchdarkly")}
                      disabled={expConnecting === "launchdarkly"}
                      className="w-full rounded-full py-2 text-sm font-medium text-white disabled:opacity-60"
                      style={{ background: "#405BFF" }}
                    >
                      {expConnecting === "launchdarkly" ? "Connecting…" : "Connect LaunchDarkly"}
                    </button>
                  </div>
                )}
              </div>

              {/* Statsig */}
              <div className="rounded-2xl border border-[var(--border)] overflow-hidden">
                <div
                  className="flex cursor-pointer items-center justify-between px-4 py-3 hover:bg-[rgba(255,255,255,0.02)]"
                  onClick={() => {
                    if (isExpConnected("statsig")) return;
                    setExpandedExpPlatform(expandedExpPlatform === "statsig" ? null : "statsig");
                    setExpConnectError(null);
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-xl text-xs font-bold text-white" style={{ background: "#EF6E23" }}>SG</span>
                    <div>
                      <p className="text-sm font-medium text-[var(--text-primary)]">Statsig</p>
                      <p className="text-xs text-[var(--text-muted)]">Server Secret Key</p>
                    </div>
                  </div>
                  {isExpConnected("statsig") ? (
                    <span className="text-xs font-medium text-[var(--success)]">✓ Connected</span>
                  ) : (
                    <span className="text-xs text-[var(--primary)]">{expandedExpPlatform === "statsig" ? "▲ Cancel" : "Connect →"}</span>
                  )}
                </div>
                {expandedExpPlatform === "statsig" && !isExpConnected("statsig") && (
                  <div className="border-t border-[var(--border)] px-4 pb-4 pt-3 space-y-3">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-[var(--text-muted)]">Server Secret Key</label>
                      <input
                        type="password"
                        placeholder="secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                        value={expFormValues.server_secret ?? ""}
                        onChange={(e) => setExpFormValues((prev) => ({ ...prev, server_secret: e.target.value }))}
                        className="w-full rounded-xl border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[#EF6E23]"
                      />
                    </div>
                    <p className="text-xs text-[var(--text-muted)]">Find your key in Statsig → Settings → Keys & Environments</p>
                    {expConnectError && <p className="text-xs text-[var(--danger)]">{expConnectError}</p>}
                    <button
                      onClick={() => handleExpPlatformConnect("statsig")}
                      disabled={expConnecting === "statsig"}
                      className="w-full rounded-full py-2 text-sm font-medium text-white disabled:opacity-60"
                      style={{ background: "#EF6E23" }}
                    >
                      {expConnecting === "statsig" ? "Connecting…" : "Connect Statsig"}
                    </button>
                  </div>
                )}
              </div>

              {/* Coming soon */}
              <div className="flex items-center justify-between rounded-2xl border border-[var(--border)] px-4 py-3 opacity-40">
                <div className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[rgba(255,255,255,0.06)] text-xs font-bold text-[var(--text-muted)]">OT</span>
                  <p className="text-sm text-[var(--text-muted)]">Optimizely, VWO, Split.io</p>
                </div>
                <span className="text-xs text-[var(--text-muted)]">Coming soon</span>
              </div>
            </div>

            <button
              onClick={() => handleGetRecommendations(pendingAnalyzeId)}
              className="mt-6 w-full rounded-full bg-[var(--primary)] py-3 text-sm font-medium text-white shadow-[0_0_20px_rgba(99,102,241,0.25)] transition hover:brightness-110"
            >
              Continue — show experiment opportunities →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
