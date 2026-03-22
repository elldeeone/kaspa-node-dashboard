import type { ReactNode } from "react";

type StatCardProps = {
  title: string;
  value: string;
  detail: string;
  icon: ReactNode;
};

export function StatCard({ title, value, detail, icon }: StatCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <div className="flex items-center justify-between pb-2">
        <h3 className="text-sm font-medium text-zinc-400">{title}</h3>
        <div className="h-4 w-4 text-zinc-500">{icon}</div>
      </div>
      <div className="text-2xl font-bold text-gray-50">{value}</div>
      <p className="text-xs text-zinc-500">{detail}</p>
    </div>
  );
}
