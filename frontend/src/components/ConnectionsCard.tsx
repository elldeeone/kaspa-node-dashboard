import type { DashboardSnapshot } from "../api/dashboard";

const MAX_PEERS = 16;
const RADIUS = 45;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

type ConnectionsCardProps = {
  peers: DashboardSnapshot["peers"] | null;
  isUtxoIndexed: boolean;
};

export function ConnectionsCard({ peers, isUtxoIndexed }: ConnectionsCardProps) {
  const peerCount = peers?.total ?? 0;
  const progress = Math.min(peerCount / MAX_PEERS, 1);
  const strokeDashoffset = CIRCUMFERENCE * (1 - progress);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold text-gray-50">Connections</h2>
      <div className="flex flex-col items-center justify-center gap-4">
        <div className="relative flex h-40 w-40 items-center justify-center" id="radialProgress">
          <svg className="absolute inset-0" viewBox="0 0 100 100">
            <circle className="text-zinc-800" cx="50" cy="50" fill="none" r={RADIUS} stroke="currentColor" strokeWidth="10" />
            <circle
              className="text-teal-400"
              cx="50"
              cy="50"
              fill="none"
              r={RADIUS}
              stroke="currentColor"
              strokeDasharray={CIRCUMFERENCE}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              strokeWidth="10"
              transform="rotate(-90 50 50)"
            />
          </svg>
          <div className="flex flex-col items-center text-center">
            <span className="text-4xl font-bold text-gray-50">{peerCount}</span>
            <span className="text-sm text-zinc-400">Peers</span>
          </div>
        </div>
        <div className="w-full space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-teal-400" />
              <span>Outbound</span>
            </div>
            <span>{peers?.outbound ?? 0}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-purple-400" />
              <span>Inbound</span>
            </div>
            <span>{peers?.inbound ?? 0}</span>
          </div>
          <div className="flex items-center justify-between pt-2">
            <span className="text-zinc-400">UTXO Indexed</span>
            <span
              className={`inline-flex items-center rounded-full border px-2 py-1 text-xs font-medium ${
                isUtxoIndexed
                  ? "border-teal-500/50 bg-teal-500/10 text-teal-400"
                  : "border-red-500/50 bg-red-500/10 text-red-400"
              }`}
            >
              {isUtxoIndexed ? "Yes" : "No"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
