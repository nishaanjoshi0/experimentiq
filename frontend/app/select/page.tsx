"use client";

import Link from "next/link";

interface SelectionCardProps {
  href: string;
  badge?: string;
  title: string;
  description: string;
  bullets: string[];
  cta: string;
  accent: "indigo" | "cyan" | "emerald";
}

const ACCENT_CLASSES = {
  indigo: {
    border: "hover:border-[rgba(99,102,241,0.5)]",
    glow: "from-[rgba(99,102,241,0.12)] to-transparent",
    cta: "bg-[var(--primary)] shadow-[0_0_24px_rgba(99,102,241,0.3)] text-white",
    dot: "bg-[var(--primary)]",
  },
  cyan: {
    border: "hover:border-[rgba(34,211,238,0.5)]",
    glow: "from-[rgba(34,211,238,0.10)] to-transparent",
    cta: "bg-[rgba(34,211,238,0.15)] border border-[rgba(34,211,238,0.4)] text-[var(--secondary)]",
    dot: "bg-[var(--secondary)]",
  },
  emerald: {
    border: "hover:border-[rgba(52,211,153,0.5)]",
    glow: "from-[rgba(52,211,153,0.10)] to-transparent",
    cta: "bg-[rgba(52,211,153,0.12)] border border-[rgba(52,211,153,0.4)] text-[var(--success)]",
    dot: "bg-[var(--success)]",
  },
};

function SelectionCard({
  href,
  badge,
  title,
  description,
  bullets,
  cta,
  accent,
}: SelectionCardProps) {
  const ac = ACCENT_CLASSES[accent];
  return (
    <Link
      href={href}
      className={`surface-panel group relative flex flex-col gap-6 overflow-hidden rounded-3xl border border-[var(--border)] p-7 transition duration-200 ${ac.border}`}
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${ac.glow} opacity-0 transition-opacity duration-300 group-hover:opacity-100`} />
      <div className="relative flex flex-col gap-4">
        {badge && (
          <span className="w-fit rounded-full border border-[var(--border)] bg-[rgba(10,10,15,0.8)] px-3 py-1 text-xs font-medium uppercase tracking-[0.16em] text-[var(--text-muted)]">
            {badge}
          </span>
        )}
        <h2 className="text-xl font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
          {title}
        </h2>
        <p className="text-sm leading-7 text-[var(--text-muted)]">{description}</p>
        <ul className="space-y-2">
          {bullets.map((b) => (
            <li key={b} className="flex items-start gap-2.5 text-xs text-[var(--text-muted)]">
              <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${ac.dot}`} />
              {b}
            </li>
          ))}
        </ul>
      </div>
      <div className="relative mt-auto">
        <span className={`inline-flex items-center rounded-full px-5 py-2.5 text-sm font-medium transition duration-150 group-hover:-translate-y-0.5 ${ac.cta}`}>
          {cta}
        </span>
      </div>
    </Link>
  );
}

export default function SelectPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-10">
      <section className="space-y-3 text-center">
        <p className="text-sm font-medium uppercase tracking-[0.24em] text-[var(--secondary)]">
          ExperimentIQ
        </p>
        <h1 className="text-4xl font-semibold tracking-[-0.05em] text-[var(--text-primary)] md:text-5xl">
          What do you want to do?
        </h1>
        <p className="mx-auto max-w-xl text-base leading-7 text-[var(--text-muted)]">
          Choose a path. You can always switch between them from any page.
        </p>
      </section>

      <div className="grid gap-5 md:grid-cols-3">
        <SelectionCard
          href="/datasets"
          badge="Dataset"
          title="Upload a dataset for recommendations"
          description="Upload your own data or pick from pre-built datasets. Get ranked experiment opportunities grounded in your actual behavioral signals."
          bullets={[
            "Google Merchandise Store, Olist, Instacart, Telco Churn",
            "Upload any GA4-compatible CSV",
            "Ranked opportunities with lift estimates",
            "One click to frame and start the experiment",
          ]}
          cta="Choose a dataset →"
          accent="indigo"
        />
        <SelectionCard
          href="/analytics"
          badge="Live data"
          title="Connect your analytics platform"
          description="Link GA4 and pull live behavioral data directly. Recommendations are grounded in your real funnel, segments, and conversion gaps — not sample data."
          bullets={[
            "Google Analytics 4 (live)",
            "Mixpanel, Amplitude — coming soon",
            "Real funnel + segment analysis",
            "Start experiments directly in GrowthBook",
          ]}
          cta="Connect analytics →"
          accent="cyan"
        />
        <SelectionCard
          href="/experiments"
          badge="Existing experiment"
          title="Evaluate an experiment"
          description="Frame a new hypothesis, monitor a running experiment for SRM and novelty effects, or get a ship/iterate/abandon recommendation on completed results."
          bullets={[
            "Hypothesis → structured design",
            "SRM detection and sequential testing",
            "Ship / iterate / abandon with evidence",
            "Defensible enough to put in a postmortem",
          ]}
          cta="Evaluate experiment →"
          accent="emerald"
        />
      </div>
    </div>
  );
}
