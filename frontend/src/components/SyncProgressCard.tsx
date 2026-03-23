import type { DashboardSnapshot } from "../api/dashboard";
import { formatCompactNumber } from "../lib/formatters";

type SyncProgressCardProps = {
  syncStatus: DashboardSnapshot["syncStatus"] | null;
  blockdag: DashboardSnapshot["blockdag"] | null;
};

function getStatusClasses(state: string | undefined) {
  switch (state) {
    case "synced":
      return {
        chip: "border-teal-500/40 bg-teal-500/10 text-teal-300",
        dot: "bg-teal-400",
      };
    case "syncing":
      return {
        chip: "border-amber-500/40 bg-amber-500/10 text-amber-200",
        dot: "bg-amber-400",
      };
    case "waiting-for-peers":
      return {
        chip: "border-orange-500/40 bg-orange-500/10 text-orange-200",
        dot: "bg-orange-400",
      };
    default:
      return {
        chip: "border-zinc-700 bg-zinc-800/80 text-zinc-300",
        dot: "bg-zinc-500",
      };
  }
}

function renderMetric(label: string, value: string) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-gray-50">{value}</p>
    </div>
  );
}

export function SyncProgressCard({ syncStatus, blockdag }: SyncProgressCardProps) {
  const styles = getStatusClasses(syncStatus?.state);
  const blockCount = blockdag ? formatCompactNumber(blockdag.blockCount) : "0";
  const headerCount = blockdag ? formatCompactNumber(blockdag.headerCount) : "0";
  const headersAhead = blockdag ? formatCompactNumber(blockdag.headersAhead) : "0";

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/70 lg:col-span-2">
      <div className="grid-background absolute inset-0" />
      <div className="relative p-4 sm:p-6">
        <div className="mb-6 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gray-50">Sync Status</h2>
          <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${styles.chip}`}>
            <span className={`h-2 w-2 rounded-full ${styles.dot}`} />
            {syncStatus?.label ?? "Connecting"}
          </span>
        </div>

        <div className="space-y-6">
          <div className="max-w-2xl">
            <h3 className="text-4xl font-bold tracking-tight text-gray-50 sm:text-5xl">{syncStatus?.label ?? "Connecting"}</h3>
            <p className="mt-3 text-sm leading-6 text-zinc-400">{syncStatus?.detail ?? "Waiting for kaspad connection"}</p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {renderMetric("Blocks", blockCount)}
            {renderMetric("Headers", headerCount)}
            {renderMetric("Header Gap", headersAhead)}
          </div>

          {syncStatus?.ibdPeerAddress ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm">
              <span className="text-zinc-400">Current sync peer</span>
              <span className="font-mono text-gray-50">{syncStatus.ibdPeerAddress}</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
