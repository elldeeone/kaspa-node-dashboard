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
      version: "v1.1.0",
      isOutbound: true,
      isIbdPeer: false,
      pingMs: 48.2,
      connected_time: 8640,
    },
    {
      id: "peer-02",
      address: "[2a01:4f9:3051:4bd2::2]:16111",
      version: "v1.1.0",
      isOutbound: true,
      isIbdPeer: false,
      pingMs: 62.4,
      connected_time: 6220,
    },
    {
      id: "peer-03",
      address: "84.17.34.90:16111",
      version: "v1.0.3",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 91.6,
      connected_time: 4900,
    },
    {
      id: "peer-04",
      address: "143.198.22.71:16111",
      version: "v1.1.0",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 73.1,
      connected_time: 2820,
    },
  ]);

  return {
    connection: {
      connected: true,
      ready: true,
      subscribed: true,
      state: "subscribed",
    },
    kaspad: {
      version: "1.1.0",
      protocolVersion: 7,
      network: "kaspa-mainnet",
      isSynced: true,
      isUtxoIndexed: true,
      p2pId: "12D3KooWMockKaspaNodeP2PExample",
      uptime: {
        uptime_formatted: "3h 14m 12s",
        uptime_seconds: 11652,
        node_start_time: null,
      },
    },
    syncProgress: {
      is_syncing: false,
      is_synced: true,
      percentage: 100,
      phase: "Sync Complete",
      details: "Node fully synced with 29,842,511 blocks",
      sub_phase: "complete",
      peer_address: null,
      error: null,
    },
    blockdag: {
      blockCount: 29842511,
      headerCount: 29842511,
      tipHashes: ["000000000000000000000000000000000000000000000000000000000000abcd"],
      pruningPoint: "000000000000000000000000000000000000000000000000000000000000beef",
      difficulty: 1123456,
      pastMedianTime: 1719999999,
      virtualDaaScore: 29842620,
      blueScore: 29842511,
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
      version: "Protocol v7",
      isOutbound: true,
      isIbdPeer: true,
      pingMs: 135.8,
      connected_time: 840,
    },
    {
      id: "peer-12",
      address: "[2604:a880:cad:d0::4d6:8001]:16111",
      version: "v1.1.0",
      isOutbound: false,
      isIbdPeer: true,
      pingMs: 188.4,
      connected_time: 590,
    },
    {
      id: "peer-13",
      address: "209.38.17.221:16111",
      version: "v1.0.2",
      isOutbound: false,
      isIbdPeer: false,
      pingMs: 92.5,
      connected_time: 1210,
    },
  ]);

  return {
    connection: {
      connected: true,
      ready: true,
      subscribed: false,
      state: "ready",
    },
    kaspad: {
      version: "1.1.0",
      protocolVersion: 7,
      network: "kaspa-mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "12D3KooWMockKaspaSyncingNode",
      uptime: {
        uptime_formatted: "41m 7s",
        uptime_seconds: 2467,
        node_start_time: null,
      },
    },
    syncProgress: {
      is_syncing: true,
      is_synced: false,
      percentage: 62.4,
      phase: "Block Download",
      details: "Downloading and validating blocks from the selected sync peer",
      message: "Downloading and validating blocks from the selected sync peer",
      sub_phase: "bulk_block_download",
      peer_address: "45.79.113.10:16111",
      error: null,
    },
    blockdag: {
      blockCount: 18620291,
      headerCount: 29842511,
      tipHashes: [],
      pruningPoint: "",
      difficulty: 0,
      pastMedianTime: 0,
      virtualDaaScore: 18620312,
      blueScore: 18620291,
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
      ready: false,
      subscribed: false,
      state: "reconnecting",
    },
    kaspad: {
      version: "1.1.0",
      protocolVersion: 7,
      network: "kaspa-mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "",
      uptime: {
        uptime_formatted: "12m 48s",
        uptime_seconds: 768,
        node_start_time: null,
      },
    },
    syncProgress: {
      is_syncing: true,
      is_synced: false,
      percentage: 18.9,
      phase: "Headers Proof IBD",
      details: "Connection to kaspad dropped, attempting to reconnect",
      message: "Connection to kaspad dropped, attempting to reconnect",
      sub_phase: "waiting_for_resubscribe",
      peer_address: null,
      error: "WebSocket disconnected, retrying...",
    },
    blockdag: {
      blockCount: 0,
      headerCount: 0,
      tipHashes: [],
      pruningPoint: "",
      difficulty: 0,
      pastMedianTime: 0,
      virtualDaaScore: 0,
      blueScore: 0,
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
      connected: true,
      ready: false,
      subscribed: false,
      state: "connecting",
    },
    kaspad: {
      version: "Unknown",
      protocolVersion: 0,
      network: "kaspa-mainnet",
      isSynced: false,
      isUtxoIndexed: false,
      p2pId: "",
      uptime: {},
    },
    syncProgress: {
      is_syncing: true,
      is_synced: false,
      percentage: 0,
      phase: "IBD Negotiation",
      details: "Waiting for the node to report its initial sync status",
      message: "Waiting for the node to report its initial sync status",
      sub_phase: null,
      peer_address: null,
      error: null,
    },
    blockdag: {
      blockCount: 0,
      headerCount: 0,
      tipHashes: [],
      pruningPoint: "",
      difficulty: 0,
      pastMedianTime: 0,
      virtualDaaScore: 0,
      blueScore: 0,
    },
    peers: buildPeers([]),
    mempool: {
      size: 0,
    },
    lastUpdate: nowIso(),
  };
}

export function getMockDashboardSnapshot(scenario: MockScenario): DashboardSnapshot {
  switch (scenario) {
    case "synced":
      return createSyncedSnapshot();
    case "syncing":
      return createSyncingSnapshot();
    case "reconnecting":
      return createReconnectingSnapshot();
    case "empty":
      return createEmptySnapshot();
  }
}

export function getRequestedMockScenario(search: string): MockScenario | null {
  const params = new URLSearchParams(search);
  const mock = params.get("mock");

  if (!mock) {
    return null;
  }

  if ((MOCK_SCENARIOS as readonly string[]).includes(mock)) {
    return mock as MockScenario;
  }

  return "synced";
}
