use std::{sync::Arc, time::Duration};

use anyhow::{Context, Result, anyhow};
use chrono::Utc;
use kaspa_rpc_core::{
    GetBlockDagInfoResponse, GetConnectedPeerInfoResponse, GetInfoResponse, GetServerInfoResponse,
    RpcPeerInfo, api::rpc::RpcApi,
};
use kaspa_wrpc_client::{KaspaRpcClient, WrpcEncoding, prelude::ConnectOptions};
use tokio::{sync::RwLock, time::timeout};
use tracing::{debug, info, warn};

use crate::{
    config::Config,
    models::{
        BlockDagSummary, ConnectionStatus, DashboardSnapshot, KaspadStatus, MempoolSummary,
        PeerSummary, PeerView, SyncStatus,
    },
};

#[derive(Clone)]
pub struct SnapshotStore {
    inner: Arc<RwLock<DashboardSnapshot>>,
}

impl SnapshotStore {
    pub fn new(snapshot: DashboardSnapshot) -> Self {
        Self {
            inner: Arc::new(RwLock::new(snapshot)),
        }
    }

    pub async fn read(&self) -> DashboardSnapshot {
        self.inner.read().await.clone()
    }

    pub async fn write(&self, snapshot: DashboardSnapshot) {
        *self.inner.write().await = snapshot;
    }
}

pub async fn connect_client(config: &Config) -> Result<Arc<KaspaRpcClient>> {
    let client = Arc::new(KaspaRpcClient::new(
        WrpcEncoding::Borsh,
        Some(&config.kaspad_wrpc_url),
        None,
        None,
        None,
    )?);
    let options = ConnectOptions {
        block_async_connect: false,
        connect_timeout: Some(Duration::from_millis(
            config.request_timeout.as_millis() as u64
        )),
        retry_interval: Some(config.refresh_interval),
        ..Default::default()
    };

    client
        .connect(Some(options))
        .await
        .context("failed to start kaspad wRPC connection")?;
    info!(url = %config.kaspad_wrpc_url, "dashboard client started");
    Ok(client)
}

pub async fn refresh_loop(store: SnapshotStore, client: Arc<KaspaRpcClient>, config: Config) {
    loop {
        let previous = store.read().await;

        let next = if client.is_connected() {
            match fetch_snapshot(&client, &config.request_timeout).await {
                Ok(snapshot) => snapshot,
                Err(error) => {
                    warn!("snapshot refresh failed: {error}");
                    stale_snapshot(
                        previous,
                        true,
                        "degraded",
                        format!("Node RPC call failed: {error}"),
                    )
                }
            }
        } else {
            let state = if previous.last_update.is_some() {
                "reconnecting"
            } else {
                "connecting"
            };
            stale_snapshot(
                previous,
                false,
                state,
                "Waiting for kaspad connection".to_string(),
            )
        };

        store.write(next).await;
        tokio::time::sleep(config.refresh_interval).await;
    }
}

async fn fetch_snapshot(
    client: &Arc<KaspaRpcClient>,
    request_timeout: &Duration,
) -> Result<DashboardSnapshot> {
    let info = call_with_timeout(request_timeout, client.get_info())
        .await
        .context("getInfo failed")?;
    let server = call_with_timeout(request_timeout, client.get_server_info())
        .await
        .context("getServerInfo failed")?;
    let blockdag = call_with_timeout(request_timeout, client.get_block_dag_info())
        .await
        .context("getBlockDagInfo failed")?;
    let peers = call_with_timeout(request_timeout, client.get_connected_peer_info())
        .await
        .context("getConnectedPeerInfo failed")?;

    let peers = map_peers(&peers.peer_info);
    let blockdag = BlockDagSummary {
        block_count: blockdag.block_count,
        header_count: blockdag.header_count,
        headers_ahead: blockdag.header_count.saturating_sub(blockdag.block_count),
        tip_hashes: blockdag
            .tip_hashes
            .iter()
            .map(ToString::to_string)
            .collect(),
        pruning_point: blockdag.pruning_point_hash.to_string(),
        difficulty: blockdag.difficulty,
        past_median_time: blockdag.past_median_time,
        virtual_daa_score: blockdag.virtual_daa_score,
        sink: blockdag.sink.to_string(),
    };

    let kaspad = KaspadStatus {
        version: server.server_version.clone(),
        network: server.network_id.to_string(),
        is_synced: server.is_synced || info.is_synced,
        is_utxo_indexed: server.has_utxo_index || info.is_utxo_indexed,
        p2p_id: info.p2p_id.clone(),
    };

    let connection = ConnectionStatus {
        connected: true,
        state: "connected".to_string(),
        message: Some("Connected to kaspad over official wRPC".to_string()),
    };

    let sync_status = SyncStatus::from_snapshot(&connection, &kaspad, &blockdag, &peers);

    Ok(DashboardSnapshot {
        connection,
        kaspad,
        sync_status,
        blockdag,
        peers,
        mempool: MempoolSummary {
            size: info.mempool_size,
        },
        last_update: Some(Utc::now()),
    })
}

fn stale_snapshot(
    mut snapshot: DashboardSnapshot,
    connected: bool,
    state: &str,
    message: String,
) -> DashboardSnapshot {
    snapshot.connection = ConnectionStatus {
        connected,
        state: state.to_string(),
        message: Some(message),
    };
    snapshot.sync_status = SyncStatus::from_snapshot(
        &snapshot.connection,
        &snapshot.kaspad,
        &snapshot.blockdag,
        &snapshot.peers,
    );
    snapshot
}

async fn call_with_timeout<T>(
    request_timeout: &Duration,
    future: impl std::future::Future<Output = kaspa_rpc_core::RpcResult<T>>,
) -> Result<T> {
    timeout(*request_timeout, future)
        .await
        .map_err(|_| anyhow!("request timed out after {}ms", request_timeout.as_millis()))?
        .map_err(|error| anyhow!(error.to_string()))
}

fn map_peers(source: &[RpcPeerInfo]) -> PeerSummary {
    let mut inbound = 0usize;
    let mut outbound = 0usize;
    let mut ibd_peer_count = 0usize;
    let mut ping_total = 0.0f64;
    let mut ping_count = 0usize;

    let details = source
        .iter()
        .map(|peer| {
            if peer.is_outbound {
                outbound += 1;
            } else {
                inbound += 1;
            }

            if peer.is_ibd_peer {
                ibd_peer_count += 1;
            }

            if peer.last_ping_duration > 0 {
                ping_total += peer.last_ping_duration as f64;
                ping_count += 1;
            }

            PeerView {
                id: peer.id.to_string(),
                address: peer.address.to_string(),
                version: normalize_peer_version(&peer.user_agent, peer.advertised_protocol_version),
                is_outbound: peer.is_outbound,
                is_ibd_peer: peer.is_ibd_peer,
                ping_ms: (peer.last_ping_duration > 0).then_some(peer.last_ping_duration as f64),
                connected_seconds: peer.time_connected / 1_000,
            }
        })
        .collect::<Vec<_>>();

    let average_ping =
        (ping_count > 0).then_some(((ping_total / ping_count as f64) * 10.0).round() / 10.0);
    debug!("mapped {} peers", details.len());

    PeerSummary {
        total: details.len(),
        inbound,
        outbound,
        average_ping,
        ibd_peer_count,
        details,
    }
}

fn normalize_peer_version(user_agent: &str, protocol_version: u32) -> String {
    let trimmed = user_agent.trim_matches('/');
    if trimmed.is_empty() {
        return if protocol_version > 0 {
            format!("Protocol v{protocol_version}")
        } else {
            "Unknown".to_string()
        };
    }

    for segment in trimmed.split('/') {
        if let Some(version) = segment.strip_prefix("kaspad:") {
            let cleaned = version.split('(').next().unwrap_or(version).trim();
            if !cleaned.is_empty() {
                return cleaned.to_string();
            }
        }
    }

    trimmed.to_string()
}

#[allow(dead_code)]
fn _keep_rpc_models_used(
    _info: &GetInfoResponse,
    _server: &GetServerInfoResponse,
    _blockdag: &GetBlockDagInfoResponse,
    _peers: &GetConnectedPeerInfoResponse,
) {
}

#[cfg(test)]
mod tests {
    use super::normalize_peer_version;

    #[test]
    fn extracts_version_from_kaspad_user_agent() {
        assert_eq!(normalize_peer_version("/kaspad:1.2.3/", 7), "1.2.3");
        assert_eq!(
            normalize_peer_version("/wallet/kaspad:1.0.5(extra)/", 7),
            "1.0.5"
        );
    }

    #[test]
    fn falls_back_to_protocol_version_when_user_agent_missing() {
        assert_eq!(normalize_peer_version("", 7), "Protocol v7");
    }
}
