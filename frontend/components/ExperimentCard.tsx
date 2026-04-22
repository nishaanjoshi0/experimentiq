"use client";

import Link from "next/link";

import type { Experiment } from "@/lib/api";

interface ExperimentCardProps {
  experiment: Experiment;
}

const statusStyles: Record<string, { badge: string; accent: string; dot: string }> = {
  running: {
    badge: "bg-[rgba(34,197,94,0.14)] text-[var(--success)]",
    accent: "before:bg-[var(--success)]",
    dot: "bg-[var(--success)]"
  },
  draft: {
    badge: "bg-[rgba(100,116,139,0.16)] text-[var(--text-muted)]",
    accent: "before:bg-[var(--text-muted)]",
    dot: "bg-[var(--text-muted)]"
  },
  completed: {
    badge: "bg-[rgba(34,211,238,0.12)] text-[var(--secondary)]",
    accent: "before:bg-[var(--secondary)]",
    dot: "bg-[var(--secondary)]"
  }
};

function formatDate(dateValue: string | null): string {
  if (!dateValue) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  }).format(new Date(dateValue));
}

export function ExperimentCard({ experiment }: ExperimentCardProps) {
  const statusStyle = statusStyles[experiment.status] ?? {
    badge: "bg-[rgba(245,158,11,0.14)] text-[var(--warning)]",
    accent: "before:bg-[var(--warning)]",
    dot: "bg-[var(--warning)]"
  };

  return (
    <Link
      href={`/experiments/${experiment.id}`}
      className={`surface-panel group relative flex h-full flex-col justify-between overflow-hidden rounded-3xl p-6 transition duration-150 ease-in hover:-translate-y-1 hover:border-[rgba(99,102,241,0.45)] hover:shadow-[0_0_40px_rgba(99,102,241,0.18)] before:absolute before:inset-y-5 before:left-0 before:w-1 before:rounded-r-full ${statusStyle.accent}`}
    >
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-3">
            <p className="metric-mono text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">
              {experiment.id}
            </p>
            <h3 className="text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)] transition duration-150 ease-in group-hover:text-white">
              {experiment.name}
            </h3>
          </div>
          <span className={`status-pill capitalize ${statusStyle.badge}`}>
            <span className={`h-2 w-2 rounded-full ${statusStyle.dot}`} />
            {experiment.status}
          </span>
        </div>
        <p className="line-clamp-2 text-sm leading-6 text-[var(--text-muted)]">{experiment.hypothesis}</p>
      </div>
      <p className="metric-mono mt-6 text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">
        Created {formatDate(experiment.createdAt)}
      </p>
    </Link>
  );
}
