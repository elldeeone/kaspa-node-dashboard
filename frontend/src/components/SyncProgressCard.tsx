import type { DashboardSnapshot } from "../api/dashboard";
import { formatCompactNumber, formatEtaDuration } from "../lib/formatters";
import { InfoTooltip } from "./InfoTooltip";

type SyncProgressCardProps = {
  syncStatus: DashboardSnapshot["syncStatus"] | null;
  blockdag: DashboardSnapshot["blockdag"] | null;
  syncEstimate: DashboardSnapshot["syncEstimate"] | null;
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

function renderMetric(
  label: string,
  value: string,
  detail: string,
  helpText: string,
  tooltipId: string,
  tooltipAlign: "left" | "right" = "right",
) {
  return (
    <div className="flex min-w-0 h-full flex-col rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
      <div className="flex min-h-[2.5rem] items-start justify-between gap-2">
        <p className="flex-1 text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</p>
        <InfoTooltip
          align={tooltipAlign}
          buttonClassName="rounded-full p-0.5 text-zinc-600 outline-none transition-colors hover:text-zinc-400 focus-visible:ring-2 focus-visible:ring-teal-400/70"
          buttonLabel={`Show ${label} help`}
          content={helpText}
          tooltipId={tooltipId}
        />
      </div>
      <p className="mt-2 min-h-[2rem] text-2xl font-semibold tracking-tight text-gray-50">{value}</p>
      <p className="mt-auto min-h-[3rem] break-words pt-3 text-xs leading-5 text-zinc-500">{detail}</p>
    </div>
  );
}

export function SyncProgressCard({ syncStatus, blockdag, syncEstimate }: SyncProgressCardProps) {
  const styles = getStatusClasses(syncStatus?.state);
  const isSynced = syncStatus?.state === "synced";
  const blockCount = blockdag ? formatCompactNumber(blockdag.blockCount) : "0";
  const headerCount = blockdag ? formatCompactNumber(blockdag.headerCount) : "0";
  const headersAhead = blockdag ? formatCompactNumber(blockdag.headersAhead) : "0";
  const virtualDaaScore = blockdag ? formatCompactNumber(blockdag.virtualDaaScore) : "0";
  const estimatedDaaLagValue = syncEstimate?.estimatedDaaLag ?? (isSynced ? 0 : null);
  const estimatedDaaLag = estimatedDaaLagValue === null ? "Calculating" : formatCompactNumber(estimatedDaaLagValue);
  const etaValue = syncEstimate?.estimatedTimeToSyncSeconds ?? (isSynced ? 0 : null);
  const eta = etaValue === null ? "Calculating" : etaValue === 0 ? "Complete" : formatEtaDuration(etaValue);

  const processedBlocksDetail = isSynced ? "Fully validated locally" : "Validated by this node";
  const headersRemainingDetail = blockdag
    ? blockdag.headersAhead > 0
      ? `Local backlog, ${headerCount} known locally`
      : "No processing backlog"
    : "Waiting for DAG state";
  const estimatedDaaLagDetail =
    isSynced
      ? "At the network tip"
      : estimatedDaaLagValue === null
        ? "Waiting for tip data"
        : "Network distance in DAA";
  const etaDetail =
    isSynced
      ? "Node is fully caught up"
      : etaValue === null
        ? "Building enough trend data"
        : "Based on recent progress";

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/70 lg:col-span-2">
      <div className="grid-background absolute inset-0" />
      <div className="relative min-w-0 p-4 sm:p-6">
        <div className="mb-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold text-gray-50">Sync Status</h2>
          <span className={`inline-flex self-start items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium sm:self-auto ${styles.chip}`}>
            <span className={`h-2 w-2 rounded-full ${styles.dot}`} />
            {syncStatus?.label ?? "Connecting"}
          </span>
        </div>

        <div className="space-y-6">
          <div className="min-w-0 max-w-2xl">
            <h3 className="text-4xl font-bold tracking-tight text-gray-50 sm:text-5xl">{syncStatus?.label ?? "Connecting"}</h3>
            <p className="mt-3 break-words text-sm leading-6 text-zinc-400">{syncStatus?.detail ?? "Waiting for kaspad connection"}</p>
          </div>

          {isSynced ? (
            <div className="rounded-2xl border border-teal-500/20 bg-teal-500/[0.08] p-5 sm:p-6">
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
                <div className="min-w-0">
                  <p className="text-xs uppercase tracking-[0.2em] text-teal-100/70">Live Tip</p>
                  <h4 className="mt-3 text-2xl font-semibold tracking-tight text-gray-50 sm:text-3xl">Fully caught up and tracking the network</h4>
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-zinc-300">
                    No backlog or lag detected. This node is validating blocks in step with the Kaspa network tip.
                  </p>
                </div>

                <div className="rounded-lg border border-teal-500/15 bg-zinc-950/60 p-4 lg:justify-self-end lg:w-[220px]">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs uppercase tracking-[0.2em] text-teal-100/70">DAA Score</p>
                    <InfoTooltip
                      align="right"
                      buttonClassName="rounded-full p-0.5 text-teal-100/40 outline-none transition-colors hover:text-teal-100/80 focus-visible:ring-2 focus-visible:ring-teal-400/70"
                      buttonLabel="Show DAA Score help"
                      content="Your node's local virtual DAA score. This Kaspa-native tip metric is reported by kaspad and should advance with the network while the node is synced."
                      tooltipId="synced-daa-score-tooltip"
                    />
                  </div>
                  <p className="mt-3 text-3xl font-semibold tracking-tight text-gray-50">{virtualDaaScore}</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-400">Local tip metric reported by kaspad.</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid auto-rows-fr gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {renderMetric(
                "Blocks Validated",
                blockCount,
                processedBlocksDetail,
                "Blocks your node has already downloaded, verified, and stored locally.",
                "blocks-validated-tooltip",
                "left",
              )}
              {renderMetric(
                "Headers Remaining",
                headersAhead,
                headersRemainingDetail,
                "Headers your node already knows about that still need full block processing. This is your local backlog, not network distance.",
                "headers-remaining-tooltip",
                "left",
              )}
              {renderMetric(
                "DAA Lag",
                estimatedDaaLag,
                estimatedDaaLagDetail,
                "Estimated distance between your node's local virtual DAA and the current network tip. This is a network-lag metric, so it will not match the headers backlog one-for-one.",
                "daa-lag-tooltip",
                "right",
              )}
              {renderMetric(
                "ETA",
                eta,
                etaDetail,
                "Estimated time to catch up based on how quickly your DAA lag and local processing backlog have been shrinking recently.",
                "eta-tooltip",
                "right",
              )}
            </div>
          )}

          {syncStatus?.ibdPeerAddress ? (
            <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 px-4 py-3 text-sm">
              <span className="text-zinc-400">Current sync peer</span>
              <span className="min-w-0 break-all font-mono text-gray-50">{syncStatus.ibdPeerAddress}</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
