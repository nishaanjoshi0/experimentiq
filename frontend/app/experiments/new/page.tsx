import { FramingWizard } from "@/components/FramingWizard";

export default function NewExperimentPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-slate-500">
          Framing Assistant
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-white">
          Turn a rough hypothesis into a real experiment plan.
        </h1>
        <p className="text-sm leading-6 text-slate-600">
          Describe the change you want to test. ExperimentIQ will propose a primary metric,
          guardrails, runtime estimate, and the tradeoffs worth watching.
        </p>
      </div>
      <FramingWizard />
    </div>
  );
}
