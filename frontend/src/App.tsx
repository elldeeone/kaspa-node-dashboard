import { useDeferredValue } from "react";
import { type DashboardSnapshot } from "./api/dashboard";
import { MOCK_SCENARIOS } from "./api/mockDashboard";
import { ConnectionsCard } from "./components/ConnectionsCard";
import { HeaderCard } from "./components/HeaderCard";
import { PeerTableCard } from "./components/PeerTableCard";
import { StatCard } from "./components/StatCard";
import { SupportCard } from "./components/SupportCard";
import { SyncProgressCard } from "./components/SyncProgressCard";
import { BoltIcon, ChartIcon, UsersIcon } from "./components/icons";
import { useDashboard } from "./hooks/useDashboard";
import { formatCompactNumber, formatLastUpdated } from "./lib/formatters";

function getConnectionsValue(snapshot: DashboardSnapshot | null) {
  return snapshot ? snapshot.peers.total.toString() : "Loading...";
}

function getConnectionsDetail(snapshot: DashboardSnapshot | null) {
  return snapshot ? `${snapshot.peers.outbound} Out / ${snapshot.peers.inbound} In` : "Loading...";
}

function getAveragePingValue(snapshot: DashboardSnapshot | null) {
  if (!snapshot) {
    return "Loading...";
  }
  return snapshot.peers.averagePing === null ? "N/A" : `${snapshot.peers.averagePing}ms`;
}

function getAveragePingDetail(snapshot: DashboardSnapshot | null) {
  if (!snapshot) {
    return "Loading...";
  }
  return snapshot.peers.ibdPeerCount === 1 ? "1 IBD peer" : `${snapshot.peers.ibdPeerCount} IBD peers`;
}

function getMempoolValue(snapshot: DashboardSnapshot | null) {
  if (!snapshot) {
    return "Loading...";
  }
  if (snapshot.mempool.size === 0) {
    return snapshot.kaspad.isSynced ? "0" : "0 (syncing)";
  }
  return formatCompactNumber(snapshot.mempool.size);
}

function getMempoolDetail(snapshot: DashboardSnapshot | null) {
  return snapshot ? `Network: ${snapshot.kaspad.network}` : "Loading...";
}

export default function App() {
  const { snapshot, requestState, requestError, lastSuccessfulUpdate, mockScenario } = useDashboard();
  const deferredPeers = useDeferredValue(snapshot?.peers.details ?? []);
  const footerTimestamp = snapshot?.lastUpdate ?? lastSuccessfulUpdate;

  return (
    <div className="flex min-h-screen w-full flex-col bg-black text-gray-200">
      <main className="flex-1 px-2 pb-8 pt-2 sm:px-4 sm:pb-10 sm:pt-4 md:px-8 md:pb-12 md:pt-8">
        <div className="mx-auto grid max-w-7xl gap-4 px-2 sm:gap-6 sm:px-4">
          {mockScenario ? (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              <p>
                Mock mode is active with the <span className="font-semibold">{mockScenario}</span> scenario.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {MOCK_SCENARIOS.map((scenario) => (
                  <a
                    className={`rounded-full border px-3 py-1 font-mono text-xs transition-colors ${
                      scenario === mockScenario
                        ? "border-amber-300/70 bg-amber-300/15 text-amber-100"
                        : "border-amber-500/30 bg-black/10 text-amber-200 hover:border-amber-400/50 hover:bg-amber-400/10"
                    }`}
                    href={`/?mock=${scenario}`}
                    key={scenario}
                  >
                    ?mock={scenario}
                  </a>
                ))}
              </div>
              <p className="mt-3 text-xs text-amber-100/80">Use these links to preview dashboard states without a running node.</p>
            </div>
          ) : null}
          <HeaderCard requestState={requestState} snapshot={snapshot} />

          <div className="grid gap-4 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
            <StatCard detail={getConnectionsDetail(snapshot)} icon={<UsersIcon />} title="Connections" value={getConnectionsValue(snapshot)} />
            <StatCard detail={getAveragePingDetail(snapshot)} icon={<BoltIcon />} title="Average Ping" value={getAveragePingValue(snapshot)} />
            <StatCard detail={getMempoolDetail(snapshot)} icon={<ChartIcon />} title="Mempool" value={getMempoolValue(snapshot)} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
            <SyncProgressCard blockdag={snapshot?.blockdag ?? null} syncStatus={snapshot?.syncStatus ?? null} />
            <ConnectionsCard isUtxoIndexed={snapshot?.kaspad.isUtxoIndexed ?? false} peers={snapshot?.peers ?? null} />
          </div>

          <SupportCard />
          <PeerTableCard peers={deferredPeers} />

          <div className="text-center text-sm text-zinc-400">
            Last updated: <span>{formatLastUpdated(footerTimestamp)}</span>
          </div>
          {requestError ? <div className="text-center text-xs text-yellow-400">{requestError}</div> : null}
          <div className="mt-2 space-y-1 text-center text-xs text-zinc-500">
            <div>
              Container maintained by{" "}
              <a className="text-teal-400 transition-colors duration-200 hover:text-teal-300" href="https://hub.docker.com/u/supertypo" target="_blank" rel="noreferrer">
                Supertypo
              </a>{" "}
              at{" "}
              <a className="text-teal-400 transition-colors duration-200 hover:text-teal-300" href="https://hub.docker.com/r/kaspanet/rusty-kaspad" target="_blank" rel="noreferrer">
                kaspanet/rusty-kaspad
              </a>
            </div>
            <div>
              Packaged with <span aria-hidden="true">&#10084;</span> by{" "}
              <a className="text-teal-400 transition-colors duration-200 hover:text-teal-300" href="https://luke.dunshea.au/" target="_blank" rel="noreferrer">
                Luke Dunshea
              </a>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
