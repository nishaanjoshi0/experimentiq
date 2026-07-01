"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ExperimentCard } from "@/components/ExperimentCard";
import {
  connectLaunchDarkly,
  connectStatsig,
  disconnectLaunchDarkly,
  disconnectStatsig,
  getExperimentPlatformStatuses,
  listExperiments,
  type AllExperimentPlatformStatus,
  type Experiment,
  type ExperimentPlatform,
} from "@/lib/api";

interface PlatformDef {
  id: ExperimentPlatform;
  label: string;
  color: string;
  borderColor: string;
  fields: { key: string; label: string; placeholder: string; defaultValue?: string; type?: string }[];
}

const PLATFORM_DEFS: PlatformDef[] = [
  {
    id: "growthbook",
    label: "GrowthBook",
    color: "var(--success)",
    borderColor: "rgba(52,211,153,0.4)",
    fields: [],
  },
  {
    id: "launchdarkly",
    label: "LaunchDarkly",
    color: "#405BFF",
    borderColor: "rgba(64,91,255,0.4)",
    fields: [
      { key: "access_token", label: "Access Token", placeholder: "api-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", type: "password" },
      { key: "project_key", label: "Project Key", placeholder: "default", defaultValue: "default" },
      { key: "environment_key", label: "Environment Key", placeholder: "test", defaultValue: "test" },
    ],
  },
  {
    id: "statsig",
    label: "Statsig",
    color: "#EF6E23",
    borderColor: "rgba(239,110,35,0.4)",
    fields: [
      { key: "server_secret", label: "Server Secret Key", placeholder: "secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", type: "password" },
    ],
  },
];

export default function ExperimentsPage() {
  const [platform, setPlatform] = useState<ExperimentPlatform>("growthbook");
  const [statuses, setStatuses] = useState<AllExperimentPlatformStatus | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Connect modal state
  const [connectingTo, setConnectingTo] = useState<ExperimentPlatform | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [connectError, setConnectError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Load platform statuses on mount
  useEffect(() => {
    void getExperimentPlatformStatuses()
      .then(setStatuses)
      .catch(() => {});
  }, []);

  function isConnected(id: ExperimentPlatform): boolean {
    if (id === "growthbook") return true;
    return statuses?.[id]?.connected ?? false;
  }

  // Load experiments whenever platform changes (and it's connected)
  useEffect(() => {
    if (!isConnected(platform)) return;
    setIsLoading(true);
    setError(null);
    listExperiments(platform)
      .then(setExperiments)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load experiments."))
      .finally(() => setIsLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, statuses]);

  function handleTabClick(id: ExperimentPlatform) {
    if (!isConnected(id)) {
      // Open connect modal
      const def = PLATFORM_DEFS.find((p) => p.id === id)!;
      const defaults: Record<string, string> = {};
      def.fields.forEach((f) => { if (f.defaultValue) defaults[f.key] = f.defaultValue; });
      setFormValues(defaults);
      setConnectError(null);
      setConnectingTo(id);
    } else {
      setPlatform(id);
    }
  }

  async function handleConnect() {
    if (!connectingTo) return;
    setIsSaving(true);
    setConnectError(null);
    try {
      if (connectingTo === "launchdarkly") {
        await connectLaunchDarkly(
          formValues.access_token ?? "",
          formValues.project_key ?? "default",
          formValues.environment_key ?? "test"
        );
      } else if (connectingTo === "statsig") {
        await connectStatsig(formValues.server_secret ?? "");
      }
      const updated = await getExperimentPlatformStatuses();
      setStatuses(updated);
      setPlatform(connectingTo);
      setConnectingTo(null);
      setFormValues({});
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : "Connection failed. Check your credentials.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDisconnect(id: ExperimentPlatform) {
    if (id === "launchdarkly") await disconnectLaunchDarkly();
    else if (id === "statsig") await disconnectStatsig();
    const updated = await getExperimentPlatformStatuses();
    setStatuses(updated);
    if (platform === id) setPlatform("growthbook");
  }

  const activeDef = PLATFORM_DEFS.find((p) => p.id === platform)!;
  const connectDef = connectingTo ? PLATFORM_DEFS.find((p) => p.id === connectingTo)! : null;

  return (
    <div className="space-y-10">
      {/* Header */}
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
              Connect your experimentation platform and get AI-powered analysis across all your running experiments.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-3 md:items-end">
            <Link
              href="/experiments/new"
              className="inline-flex items-center justify-center rounded-full bg-[var(--primary)] px-5 py-3 text-sm font-medium text-white shadow-[0_0_24px_rgba(99,102,241,0.3)] transition hover:-translate-y-0.5 hover:brightness-110"
            >
              New Experiment
            </Link>
            <Link href="/select" className="text-xs text-[var(--text-muted)] transition hover:text-[var(--text-primary)]">
              ← Back to hub
            </Link>
          </div>
        </div>
      </section>

      {/* Experiment feed + platform toggle */}
      <section className="space-y-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
              Experiment Feed
            </h2>
            {!isLoading && isConnected(platform) && (
              <span className="metric-mono text-sm text-[var(--text-muted)]">· {experiments.length}</span>
            )}
          </div>

          {/* Platform tabs */}
          <div className="flex items-center gap-1 rounded-full border border-[var(--border)] bg-[rgba(10,10,15,0.6)] p-1">
            {PLATFORM_DEFS.map((p) => {
              const connected = isConnected(p.id);
              const isActive = platform === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => handleTabClick(p.id)}
                  className={`relative rounded-full px-4 py-1.5 text-xs font-medium transition-all duration-150 ${
                    isActive
                      ? "bg-[var(--surface-elevated)] shadow-sm"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                  style={isActive ? { color: p.color } : {}}
                >
                  {p.label}
                  {/* dot indicator */}
                  {connected && p.id !== "growthbook" && (
                    <span
                      className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-[rgba(10,10,15,0.8)]"
                      style={{ background: p.color }}
                    />
                  )}
                  {!connected && p.id !== "growthbook" && (
                    <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-[rgba(10,10,15,0.8)] bg-[var(--border)]" />
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Not connected state */}
        {!isConnected(platform) ? (
          <div className="surface-panel rounded-3xl border border-dashed p-12 text-center">
            <p className="text-lg font-medium text-[var(--text-primary)]">{activeDef.label} not connected</p>
            <p className="mt-2 text-sm text-[var(--text-muted)]">Connect your account to see your experiments here.</p>
            <button
              onClick={() => handleTabClick(platform)}
              className="mt-6 inline-flex items-center justify-center rounded-full px-6 py-2.5 text-sm font-medium text-white transition hover:-translate-y-0.5"
              style={{ background: activeDef.color }}
            >
              Connect {activeDef.label} →
            </button>
          </div>
        ) : isLoading ? (
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
              {platform === "growthbook"
                ? "Frame a new hypothesis to get started."
                : `Create an experiment in ${activeDef.label} and it will appear here.`}
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {experiments.map((e) => (
              <ExperimentCard key={e.id} experiment={e} />
            ))}
          </div>
        )}

        {/* Disconnect link for third-party platforms */}
        {isConnected(platform) && platform !== "growthbook" && (
          <div className="text-right">
            <button
              onClick={() => handleDisconnect(platform)}
              className="text-xs text-[var(--text-muted)] transition hover:text-[var(--danger)]"
            >
              Disconnect {activeDef.label}
            </button>
          </div>
        )}
      </section>

      {/* Connect modal */}
      {connectingTo && connectDef && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => { setConnectingTo(null); setConnectError(null); }}
        >
          <div
            className="surface-panel w-full max-w-md rounded-3xl border border-[var(--border)] p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h3 className="text-xl font-semibold text-[var(--text-primary)]">
                  Connect {connectDef.label}
                </h3>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Your credentials are stored securely and never shared.
                </p>
              </div>
              <button
                onClick={() => { setConnectingTo(null); setConnectError(null); }}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              {connectDef.fields.map((f) => (
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

              {connectError && (
                <p className="text-xs text-[var(--danger)]">{connectError}</p>
              )}

              <button
                onClick={handleConnect}
                disabled={isSaving}
                className="w-full rounded-full py-2.5 text-sm font-medium text-white transition disabled:opacity-60"
                style={{ background: connectDef.color }}
              >
                {isSaving ? "Connecting…" : `Connect ${connectDef.label}`}
              </button>

              {connectingTo === "launchdarkly" && (
                <p className="text-center text-xs text-[var(--text-muted)]">
                  Find your Access Token in LaunchDarkly → Settings → Authorization → Access Tokens
                </p>
              )}
              {connectingTo === "statsig" && (
                <p className="text-center text-xs text-[var(--text-muted)]">
                  Find your Server Secret in Statsig → Settings → Keys &amp; Environments → Server Secret Keys
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
