import { z } from "zod";

const peerSchema = z.object({
  id: z.string().catch(""),
  address: z.string().catch(""),
  version: z.string().catch("Unknown"),
  isOutbound: z.boolean().catch(false),
  isIbdPeer: z.boolean().catch(false),
  pingMs: z.coerce.number().nullable().catch(null),
  connected_time: z.coerce.number().catch(0),
});

const uptimeSchema = z
  .object({
    uptime_formatted: z.string().optional(),
    uptime_seconds: z.coerce.number().optional(),
    node_start_time: z.string().nullable().optional(),
  })
  .passthrough()
  .catch({});

export const dashboardSnapshotSchema = z.object({
  connection: z.object({
    connected: z.boolean().catch(false),
    ready: z.boolean().catch(false),
    subscribed: z.boolean().optional().default(false),
    state: z.string().catch("unknown"),
  }),
  kaspad: z.object({
    version: z.string().catch("Unknown"),
    protocolVersion: z.coerce.number().catch(0),
    network: z.string().catch("kaspa-mainnet"),
    isSynced: z.boolean().catch(false),
    isUtxoIndexed: z.boolean().catch(false),
    p2pId: z.string().catch(""),
    uptime: uptimeSchema,
  }),
  syncProgress: z.object({
    is_syncing: z.boolean().optional(),
    is_synced: z.boolean().optional(),
    percentage: z.coerce.number().catch(0),
    phase: z.string().catch("Unknown"),
    details: z.string().optional(),
    message: z.string().optional(),
    sub_phase: z.string().nullable().optional(),
    peer_address: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
  }),
  blockdag: z.object({
    blockCount: z.coerce.number().catch(0),
    headerCount: z.coerce.number().catch(0),
    tipHashes: z.array(z.string()).catch([]),
    pruningPoint: z.string().catch(""),
    difficulty: z.coerce.number().catch(0),
    pastMedianTime: z.coerce.number().catch(0),
    virtualDaaScore: z.coerce.number().catch(0),
    blueScore: z.coerce.number().catch(0),
  }),
  peers: z.object({
    total: z.coerce.number().catch(0),
    inbound: z.coerce.number().catch(0),
    outbound: z.coerce.number().catch(0),
    averagePing: z.coerce.number().nullable().catch(null),
    ibdPeerCount: z.coerce.number().catch(0),
    details: z.array(peerSchema).catch([]),
  }),
  mempool: z.object({
    size: z.coerce.number().catch(0),
  }),
  lastUpdate: z.string().nullable().optional(),
});

export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;
export type DashboardPeer = z.infer<typeof peerSchema>;

export async function fetchDashboardSnapshot(signal?: AbortSignal): Promise<DashboardSnapshot> {
  const response = await fetch(`/api/info/dashboard?t=${Date.now()}`, {
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Dashboard request failed with ${response.status}`);
  }

  const payload = await response.json();

  if (payload?.error) {
    throw new Error(payload.message || "Dashboard data is unavailable");
  }

  return dashboardSnapshotSchema.parse(payload);
}
