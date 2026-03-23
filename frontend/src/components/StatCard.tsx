import type { ReactNode } from "react";
import { InfoTooltip } from "./InfoTooltip";

type StatCardProps = {
  title: string;
  value: string;
  detail: string;
  icon: ReactNode;
  helpText?: string;
};

export function StatCard({ title, value, detail, icon, helpText }: StatCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <div className="flex items-center justify-between pb-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-medium text-zinc-400">{title}</h3>
          {helpText ? (
            <InfoTooltip
              buttonClassName="rounded-full p-0.5 text-zinc-600 outline-none transition-colors hover:text-zinc-400 focus-visible:ring-2 focus-visible:ring-teal-400/70"
              buttonLabel={`Show ${title} help`}
              content={helpText}
              tooltipId={`${title.toLowerCase().replace(/\s+/g, "-")}-tooltip`}
            />
          ) : null}
        </div>
        <div className="h-4 w-4 text-zinc-500">{icon}</div>
      </div>
      <div className="text-2xl font-bold text-gray-50">{value}</div>
      <p className="text-xs text-zinc-500">{detail}</p>
    </div>
  );
}
