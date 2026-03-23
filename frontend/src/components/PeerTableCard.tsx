import type { DashboardPeer } from "../api/dashboard";
import { formatDuration, formatPeerVersion } from "../lib/formatters";
import { WifiIcon } from "./icons";

type PeerTableCardProps = {
  peers: DashboardPeer[];
};

function renderDirectionBadge(isOutbound: boolean) {
  if (isOutbound) {
    return (
      <span className="inline-flex items-center rounded-full border border-teal-500/50 bg-teal-500/10 px-2 py-1 text-xs font-medium text-teal-400">
        OUT
      </span>
    );
  }

  return (
    <span className="inline-flex items-center rounded-full border border-purple-500/50 bg-purple-500/10 px-2 py-1 text-xs font-medium text-purple-400">
      IN
    </span>
  );
}

function renderPingClass(pingMs: number | null) {
  if (pingMs === null) {
    return "text-zinc-500";
  }
  if (pingMs > 1000) {
    return "text-red-400";
  }
  if (pingMs > 500) {
    return "text-yellow-400";
  }
  return "text-green-400";
}

export function PeerTableCard({ peers }: PeerTableCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <WifiIcon className="h-5 w-5 text-zinc-400" />
        <h2 className="text-lg font-semibold text-gray-50">Connected Peers</h2>
      </div>
      <p className="mb-4 text-sm text-zinc-400">A list of peers currently connected to your node.</p>
      <div className="custom-scrollbar overflow-x-auto">
        <table className="peer-table w-full">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="px-2 py-2 text-left font-medium text-zinc-300">Peer</th>
              <th className="px-2 py-2 text-left font-medium text-zinc-300">Version</th>
              <th className="px-2 py-2 text-center font-medium text-zinc-300">Direction</th>
              <th className="px-2 py-2 text-right font-medium text-zinc-300">Ping</th>
              <th className="px-2 py-2 text-right font-medium text-zinc-300">Connected</th>
            </tr>
          </thead>
          <tbody>
            {peers.length === 0 ? (
              <tr>
                <td className="py-8 text-center text-zinc-400" colSpan={5}>
                  No peers connected
                </td>
              </tr>
            ) : (
              peers.map((peer) => (
                <tr className="border-b border-zinc-800 hover:bg-zinc-800/50" key={`${peer.id}-${peer.address}`}>
                  <td className="px-2 py-3 font-mono text-sm text-zinc-300">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="block min-w-0 truncate" title={peer.address || "Unknown"}>
                        {peer.address || "Unknown"}
                      </span>
                      {peer.isIbdPeer ? (
                        <span className="inline-flex flex-shrink-0 items-center rounded-full border border-orange-500/50 bg-orange-500/10 px-2 py-1 text-xs font-medium text-orange-400">
                          IBD
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-2 py-3">
                    <span className="inline-flex items-center rounded-full bg-zinc-700 px-2 py-1 text-xs font-medium text-zinc-300">
                      {formatPeerVersion(peer.version)}
                    </span>
                  </td>
                  <td className="px-2 py-3 text-center">{renderDirectionBadge(peer.isOutbound)}</td>
                  <td className={`px-2 py-3 text-right font-medium ${renderPingClass(peer.pingMs)}`}>
                    {peer.pingMs === null ? "N/A" : `${peer.pingMs}ms`}
                  </td>
                  <td className="px-2 py-3 text-right text-sm text-zinc-400">{formatDuration(peer.connectedSeconds)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
