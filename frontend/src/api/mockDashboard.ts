import type { DashboardSnapshot } from "./dashboard";

export const MOCK_SCENARIOS = ["synced", "syncing", "reconnecting", "empty"] as const;

export type MockScenario = (typeof MOCK_SCENARIOS)[number];

type PeerSeed = DashboardSnapshot["peers"]["details"][number];

function nowIso() {
  return new Date().toISOString();
}

function buildPeers(peers: PeerSeed[]) {
  const inbound = peers.filter((peer) => !peer.isOutbound).length;
  const outbound = peers.filter((peer) => peer.isOutbound).length;
  const ibdPeerCount = peers.filter((peer) => peer.isIbdPeer).length;
  const pingValues = peers.map((peer) => peer.pingMs).filter((value): value is number => value !== null);
  const averagePing = pingValues.length ? Number((pingValues.reduce((sum, value) => sum + value, 0) / pingValues.length).toFixed(1)) : null;

  return {
    total: peers.length,
    inbound,
    outbound,
    averagePing,
    ibdPeerCount,
    details: peers,
  };
}

function createSyncedSnapshot(): DashboardSnapshot {
  const peers = buildPeers([
    {
      id: "peer-01",
      address: "95.216.10.14:16111",
      version: "1.1.0",
      isOutbound: true,
      isIbdPeer: false,
      pingMs: 48.2,
      connectedSeconds: 8640,
    },
    {
      id: "peer-02",
      address: "[2a01:4f9:3051:4bd2::2]:16111",
      version: "1.1.0",
      isOutbound: true,
      isIbdPeer: false,
      pingMs: 62.4,
      connectedSeconds: 6220,
    },
    {
      id: "peer-03",
      address: "84.17.34.90:16111",
      version: "1.0.3",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 91.6,
      connectedSeconds: 4900,
    },
    {
      id: "peer-04",
      address: "143.198.22.71:16111",
      version: "1.1.0",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 73.1,
      connectedSeconds: 2820,
    },
  ]);

  return {
    connection: {
      connected: true,
      state: "connected",
      message: "Connected to kaspad over official wRPC",
    },
    kaspad: {
      version: "1.1.0",
      network: "mainnet",
      isSynced: true,
      isUtxoIndexed: true,
      p2pId: "12D3KooWMockKaspaNodeP2PExample",
    },
    syncStatus: {
      state: "synced",
      label: "Synced",
      detail: "Node is synced with the network tip.",
      ibdPeerAddress: null,
    },
    blockdag: {
      blockCount: 29842511,
      headerCount: 29842511,
      headersAhead: 0,
      tipHashes: ["000000000000000000000000000000000000000000000000000000000000abcd"],
      pruningPoint: "000000000000000000000000000000000000000000000000000000000000beef",
      difficulty: 1123456,
      pastMedianTime: 1719999999,
      virtualDaaScore: 29842620,
      sink: "000000000000000000000000000000000000000000000000000000000000cafe",
    },
    syncEstimate: {
      estimatedDaaLag: null,
      estimatedTimeToSyncSeconds: null,
      referenceDaaScore: null,
      referenceFetchedAt: null,
      referenceSource: null,
    },
    peers,
    mempool: {
      size: 1287,
    },
    lastUpdate: nowIso(),
  };
}

function createSyncingSnapshot(): DashboardSnapshot {
  const peers = buildPeers([
    {
      id: "peer-11",
      address: "45.79.113.10:16111",
      version: "1.1.0",
      isOutbound: true,
      isIbdPeer: true,
      pingMs: 135.8,
      connectedSeconds: 840,
    },
    {
      id: "peer-12",
      address: "[2604:a880:cad:d0::4d6:8001]:16111",
      version: "1.1.0",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 188.4,
      connectedSeconds: 590,
    },
    {
      id: "peer-13",
      address: "209.38.17.221:16111",
      version: "1.0.2",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 92.5,
      connectedSeconds: 1210,
    },
  ]);

  return {
    connection: {
      connected: true,
      state: "connected",
      message: "Connected to kaspad over official wRPC",
    },
    kaspad: {
      version: "1.1.0",
      network: "mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "12D3KooWMockKaspaSyncingNode",
    },
    syncStatus: {
      state: "syncing",
      label: "Syncing",
      detail: "About 11,222,220 DAA behind with 11,222,220 headers left to process.",
      ibdPeerAddress: "45.79.113.10:16111",
    },
    blockdag: {
      blockCount: 18620291,
      headerCount: 29842511,
      headersAhead: 11222220,
      tipHashes: ["0000000000000000000000000000000000000000000000000000000000001111"],
      pruningPoint: "0000000000000000000000000000000000000000000000000000000000002222",
      difficulty: 1098765,
      pastMedianTime: 1719991123,
      virtualDaaScore: 18620312,
      sink: "0000000000000000000000000000000000000000000000000000000000003333",
    },
    syncEstimate: {
      estimatedDaaLag: 11222220,
      estimatedTimeToSyncSeconds: 21600,
      referenceDaaScore: 29842532,
      referenceFetchedAt: nowIso(),
      referenceSource: "api.kaspa.org",
    },
    peers,
    mempool: {
      size: 0,
    },
    lastUpdate: nowIso(),
  };
}

function createReconnectingSnapshot(): DashboardSnapshot {
  return {
    connection: {
      connected: false,
      state: "reconnecting",
      message: "Waiting for kaspad connection",
    },
    kaspad: {
      version: "1.1.0",
      network: "mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "",
    },
    syncStatus: {
      state: "reconnecting",
      label: "Reconnecting",
      detail: "Waiting for kaspad connection",
      ibdPeerAddress: null,
    },
    blockdag: {
      blockCount: 18620291,
      headerCount: 29842511,
      headersAhead: 11222220,
      tipHashes: [],
      pruningPoint: "",
      difficulty: 0,
      pastMedianTime: 0,
      virtualDaaScore: 0,
      sink: "",
    },
    syncEstimate: {
      estimatedDaaLag: 11222220,
      estimatedTimeToSyncSeconds: 21600,
      referenceDaaScore: 29842532,
      referenceFetchedAt: nowIso(),
      referenceSource: "api.kaspa.org",
    },
    peers: buildPeers([]),
    mempool: {
      size: 0,
    },
    lastUpdate: nowIso(),
  };
}

function createEmptySnapshot(): DashboardSnapshot {
  return {
    connection: {
      connected: false,
      state: "connecting",
      message: "Waiting for kaspad connection",
    },
    kaspad: {
      version: "Unknown",
      network: "mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "",
    },
    syncStatus: {
      state: "connecting",
      label: "Connecting",
      detail: "Waiting for kaspad connection",
      ibdPeerAddress: null,
    },
    blockdag: {
      blockCount: 0,
      headerCount: 0,
      headersAhead: 0,
      tipHashes: [],
      pruningPoint: "",
      difficulty: 0,
      pastMedianTime: 0,
      virtualDaaScore: 0,
      sink: "",
    },
    syncEstimate: {
      estimatedDaaLag: null,
      estimatedTimeToSyncSeconds: null,
      referenceDaaScore: null,
      referenceFetchedAt: null,
      referenceSource: "api.kaspa.org",
    },
    peers: buildPeers([]),
    mempool: {
      size: 0,
    },
    lastUpdate: nowIso(),
  };
}

const SNAPSHOTS: Record<MockScenario, () => DashboardSnapshot> = {
  synced: createSyncedSnapshot,
  syncing: createSyncingSnapshot,
  reconnecting: createReconnectingSnapshot,
  empty: createEmptySnapshot,
};

export function getRequestedMockScenario(search: string): MockScenario | null {
  const params = new URLSearchParams(search);
  const value = params.get("mock");
  return value && value in SNAPSHOTS ? (value as MockScenario) : null;
}

export function getMockDashboardSnapshot(scenario: MockScenario): DashboardSnapshot {
  return SNAPSHOTS[scenario]();
}
