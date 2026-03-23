import { z } from "zod";

const peerSchema = z.object({
  id: z.string().catch(""),
  address: z.string().catch(""),
  version: z.string().catch("Unknown"),
  isOutbound: z.boolean().catch(false),
  isIbdPeer: z.boolean().catch(false),
  pingMs: z.coerce.number().nullable().catch(null),
  connectedSeconds: z.coerce.number().catch(0),
});

export const dashboardSnapshotSchema = z.object({
  connection: z.object({
    connected: z.boolean().catch(false),
    state: z.string().catch("connecting"),
    message: z.string().nullable().optional(),
  }),
  kaspad: z.object({
    version: z.string().catch("Unknown"),
    network: z.string().catch("mainnet"),
    isSynced: z.boolean().catch(false),
    isUtxoIndexed: z.boolean().catch(false),
    p2pId: z.string().catch(""),
  }),
  syncStatus: z.object({
    state: z.string().catch("connecting"),
    label: z.string().catch("Connecting"),
    detail: z.string().catch("Waiting for kaspad connection"),
    ibdPeerAddress: z.string().nullable().optional(),
  }),
  blockdag: z.object({
    blockCount: z.coerce.number().catch(0),
    headerCount: z.coerce.number().catch(0),
    headersAhead: z.coerce.number().catch(0),
    tipHashes: z.array(z.string()).catch([]),
    pruningPoint: z.string().catch(""),
    difficulty: z.coerce.number().catch(0),
    pastMedianTime: z.coerce.number().catch(0),
    virtualDaaScore: z.coerce.number().catch(0),
    sink: z.string().catch(""),
  }),
  syncEstimate: z.object({
    estimatedDaaLag: z.coerce.number().nullable().catch(null),
    estimatedTimeToSyncSeconds: z.coerce.number().nullable().catch(null),
    referenceDaaScore: z.coerce.number().nullable().catch(null),
    referenceFetchedAt: z.string().nullable().optional(),
    referenceSource: z.string().nullable().optional(),
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
  const response = await fetch(`/api/dashboard?t=${Date.now()}`, {
    signal,
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`Dashboard request failed with ${response.status}`);
  }

  return dashboardSnapshotSchema.parse(await response.json());
}
