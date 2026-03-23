use chrono::{DateTime, Utc};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DashboardSnapshot {
    pub connection: ConnectionStatus,
    pub kaspad: KaspadStatus,
    pub sync_status: SyncStatus,
    pub blockdag: BlockDagSummary,
    pub sync_estimate: SyncEstimate,
    pub peers: PeerSummary,
    pub mempool: MempoolSummary,
    pub last_update: Option<DateTime<Utc>>,
}

impl Default for DashboardSnapshot {
    fn default() -> Self {
        let blockdag = BlockDagSummary::default();
        let sync_estimate = SyncEstimate::default();
        let peers = PeerSummary::default();
        let kaspad = KaspadStatus::default();
        let connection = ConnectionStatus {
            connected: false,
            state: "connecting".to_string(),
            message: Some("Waiting for kaspad connection".to_string()),
        };
        let sync_status =
            SyncStatus::from_snapshot(&connection, &kaspad, &blockdag, &sync_estimate, &peers);

        Self {
            connection,
            kaspad,
            sync_status,
            blockdag,
            sync_estimate,
            peers,
            mempool: MempoolSummary::default(),
            last_update: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct ConnectionStatus {
    pub connected: bool,
    pub state: String,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct KaspadStatus {
    pub version: String,
    pub network: String,
    pub is_synced: bool,
    pub is_utxo_indexed: bool,
    pub p2p_id: String,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SyncStatus {
    pub state: String,
    pub label: String,
    pub detail: String,
    pub ibd_peer_address: Option<String>,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct SyncEstimate {
    pub estimated_daa_lag: Option<u64>,
    pub estimated_time_to_sync_seconds: Option<u64>,
    pub reference_daa_score: Option<u64>,
    pub reference_fetched_at: Option<DateTime<Utc>>,
    pub reference_source: Option<String>,
}

impl SyncStatus {
    pub fn from_snapshot(
        connection: &ConnectionStatus,
        kaspad: &KaspadStatus,
        blockdag: &BlockDagSummary,
        sync_estimate: &SyncEstimate,
        peers: &PeerSummary,
    ) -> Self {
        if !connection.connected {
            return Self {
                state: connection.state.clone(),
                label: match connection.state.as_str() {
                    "reconnecting" => "Reconnecting".to_string(),
                    _ => "Connecting".to_string(),
                },
                detail: connection
                    .message
                    .clone()
                    .unwrap_or_else(|| "Waiting for kaspad connection".to_string()),
                ibd_peer_address: None,
            };
        }

        if kaspad.is_synced {
            return Self {
                state: "synced".to_string(),
                label: "Synced".to_string(),
                detail: "Node is synced with the network tip.".to_string(),
                ibd_peer_address: None,
            };
        }

        if peers.total == 0 {
            return Self {
                state: "waiting-for-peers".to_string(),
                label: "Waiting for peers".to_string(),
                detail:
                    "Connected to kaspad, but the node has not established any peer sessions yet"
                        .to_string(),
                ibd_peer_address: None,
            };
        }

        let ibd_peer_address = peers
            .details
            .iter()
            .find(|peer| peer.is_ibd_peer)
            .map(|peer| peer.address.clone());
        let detail = match (
            sync_estimate.estimated_daa_lag,
            blockdag.headers_ahead,
            sync_estimate.reference_source.as_deref(),
            ibd_peer_address.as_ref(),
        ) {
            (Some(daa_lag), headers_ahead, _, _) if daa_lag > 0 && headers_ahead > 0 => format!(
                "About {} DAA behind with {} headers left to process.",
                format_number(daa_lag),
                format_number(headers_ahead)
            ),
            (Some(daa_lag), _, _, _) if daa_lag > 0 => format!(
                "About {} DAA behind the network tip.",
                format_number(daa_lag)
            ),
            (_, headers_ahead, Some(_), Some(_)) if headers_ahead > 0 => format!(
                "Estimating network lag with {} headers left to process.",
                format_number(headers_ahead)
            ),
            (_, headers_ahead, _, Some(_)) if headers_ahead > 0 => format!(
                "Processing {} remaining headers.",
                format_number(headers_ahead)
            ),
            (_, _, _, Some(_)) => {
                "Downloading and validating data from the current sync peer.".to_string()
            }
            (_, headers_ahead, Some(_), _) if headers_ahead > 0 => format!(
                "Estimating network lag with {} headers left to process.",
                format_number(headers_ahead)
            ),
            (_, headers_ahead, _, _) if headers_ahead > 0 => format!(
                "Processing {} remaining headers.",
                format_number(headers_ahead)
            ),
            _ => "Catching up with the network.".to_string(),
        };

        Self {
            state: "syncing".to_string(),
            label: "Syncing".to_string(),
            detail,
            ibd_peer_address,
        }
    }
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct BlockDagSummary {
    pub block_count: u64,
    pub header_count: u64,
    pub headers_ahead: u64,
    pub tip_hashes: Vec<String>,
    pub pruning_point: String,
    pub difficulty: f64,
    pub past_median_time: u64,
    pub virtual_daa_score: u64,
    pub sink: String,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PeerSummary {
    pub total: usize,
    pub inbound: usize,
    pub outbound: usize,
    pub average_ping: Option<f64>,
    pub ping_sample_count: usize,
    pub ibd_peer_count: usize,
    pub details: Vec<PeerView>,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct PeerView {
    pub id: String,
    pub address: String,
    pub version: String,
    pub is_outbound: bool,
    pub is_ibd_peer: bool,
    pub ping_ms: Option<f64>,
    pub connected_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct MempoolSummary {
    pub size: u64,
}

pub fn format_number(value: u64) -> String {
    let digits = value.to_string();
    let mut result = String::with_capacity(digits.len() + digits.len() / 3);

    for (index, ch) in digits.chars().rev().enumerate() {
        if index > 0 && index % 3 == 0 {
            result.push(',');
        }
        result.push(ch);
    }

    result.chars().rev().collect()
}
