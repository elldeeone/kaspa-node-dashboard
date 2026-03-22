import type { DashboardSnapshot } from "../api/dashboard";
import { formatSubPhase } from "../lib/formatters";
import { SYNC_PHASES, formatProgressLabel, getSyncMessage, isSyncComplete, mapSyncPhase } from "../lib/sync";

type SyncProgressCardProps = {
  syncProgress: DashboardSnapshot["syncProgress"] | null;
};

export function SyncProgressCard({ syncProgress }: SyncProgressCardProps) {
  const currentPhase = mapSyncPhase(syncProgress);
  const isComplete = isSyncComplete(syncProgress);
  const currentPhaseIndex = SYNC_PHASES.indexOf(currentPhase);
  const subPhase = syncProgress?.sub_phase ?? null;
  const showSubPhase = Boolean(subPhase) && !isComplete;

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/70 lg:col-span-2">
      <div className="grid-background absolute inset-0" />
      <div className="relative p-4 sm:p-6">
        <div className="mb-6 flex items-center gap-2">
          <div className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-teal-500" />
          </div>
          <h2 className="text-lg font-semibold text-gray-50">Sync Progress</h2>
        </div>
        <div className="flex flex-col items-center justify-center gap-6 pt-4">
          <div className="flex w-full items-start justify-center px-2 sm:px-4 md:px-8" id="syncPhaseIndicator">
            {SYNC_PHASES.map((phase, index) => {
              const isCompleted = isComplete || index < currentPhaseIndex;
              const isCurrent = !isComplete && index === currentPhaseIndex;

              return (
                <div className="flex w-full items-start" key={phase}>
                  <div className="flex flex-1 flex-col items-center gap-2">
                    <div
                      className={`relative flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                        isCompleted ? "border-teal-400 bg-teal-400" : "border-zinc-600"
                      } ${isCurrent ? "border-teal-400" : ""}`}
                    >
                      {isCompleted ? (
                        <svg className="h-5 w-5 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                        </svg>
                      ) : null}
                      {isCurrent ? (
                        <>
                          <span className="absolute h-full w-full animate-ping rounded-full bg-teal-400 opacity-75" />
                          <div className="h-3 w-3 rounded-full bg-teal-400" />
                        </>
                      ) : null}
                    </div>
                    <p className={`text-center text-xs font-medium transition-colors duration-300 ${isCompleted || isCurrent ? "text-gray-200" : "text-zinc-500"}`}>
                      {phase}
                    </p>
                  </div>
                  {index < SYNC_PHASES.length - 1 ? (
                    <div className={`relative top-4 mx-2 h-0.5 flex-1 rounded-full transition-colors duration-300 ${isCompleted ? "bg-teal-400" : "bg-zinc-600"}`} />
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="text-center">
            <p className="mb-4 text-sm text-zinc-400">{getSyncMessage(syncProgress)}</p>
            <h2 className="mt-1 text-6xl font-bold tracking-tighter text-gray-50">{formatProgressLabel(syncProgress)}</h2>
            <p className="text-xs text-zinc-500">Overall Progress</p>
          </div>
          {showSubPhase ? (
            <div className="flex flex-wrap items-center justify-center gap-1 text-center">
              <span className="text-sm text-zinc-400">Sub-Phase:</span>
              <span className="text-sm text-gray-50">{formatSubPhase(subPhase)}</span>
            </div>
          ) : null}
          {syncProgress?.peer_address ? (
            <div className="flex flex-wrap items-center justify-center gap-1 text-center">
              <span className="text-sm text-zinc-400">Sync Peer:</span>
              <span className="text-sm text-gray-50">{syncProgress.peer_address}</span>
            </div>
          ) : null}
          {syncProgress?.error ? (
            <div className="flex flex-wrap items-center justify-center gap-1 text-center">
              <span className="text-sm text-zinc-400">Error:</span>
              <span className="text-sm text-red-400">{syncProgress.error}</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
