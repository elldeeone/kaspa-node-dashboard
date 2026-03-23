use std::{collections::VecDeque, sync::Arc, time::Duration};

use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Utc};
use kaspa_rpc_core::{
    GetBlockDagInfoResponse, GetConnectedPeerInfoResponse, GetInfoResponse, GetServerInfoResponse,
    RpcPeerInfo, api::rpc::RpcApi,
};
use kaspa_wrpc_client::{KaspaRpcClient, WrpcEncoding, prelude::ConnectOptions};
use reqwest::Client as HttpClient;
use serde::{Deserialize, Deserializer, de};
use serde_json::Value;
use tokio::{sync::RwLock, time::timeout};
use tracing::{debug, info, warn};

use crate::{
    config::Config,
    models::{
        BlockDagSummary, ConnectionStatus, DashboardSnapshot, KaspadStatus, MempoolSummary,
        PeerSummary, PeerView, SyncEstimate, SyncStatus,
    },
};

const ETA_HISTORY_WINDOW_SECONDS: i64 = 60 * 60;
const MIN_ETA_WINDOW_SECONDS: i64 = 10 * 60;
const MAX_REFERENCE_EXTRAPOLATION_SECONDS: f64 = 60.0 * 60.0;

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

#[derive(Debug, Clone)]
struct ReferenceTipSample {
    virtual_daa_score: u64,
    fetched_at: DateTime<Utc>,
}

#[derive(Debug, Clone)]
struct ProgressSample {
    observed_at: DateTime<Utc>,
    estimated_daa_lag: Option<u64>,
    headers_ahead: u64,
}

#[derive(Debug, Default)]
struct SyncEstimator {
    latest_reference_tip: Option<ReferenceTipSample>,
    previous_reference_tip: Option<ReferenceTipSample>,
    progress_history: VecDeque<ProgressSample>,
}

impl SyncEstimator {
    fn new() -> Self {
        Self::default()
    }

    async fn update(
        &mut self,
        reference_client: &HttpClient,
        config: &Config,
        kaspad: &KaspadStatus,
        blockdag: &BlockDagSummary,
    ) -> SyncEstimate {
        let now = Utc::now();

        if kaspad.is_synced {
            self.reset();
            return SyncEstimate::default();
        }

        if self.should_refresh_reference(now, config)
            && let Err(error) = self
                .refresh_reference_tip(reference_client, config, now)
                .await
        {
            warn!("reference tip refresh failed: {error}");
        }

        let reference_daa_score = self.estimated_reference_daa_score(now, config);
        let estimated_daa_lag =
            reference_daa_score.map(|score| score.saturating_sub(blockdag.virtual_daa_score));

        self.record_progress(now, estimated_daa_lag, blockdag.headers_ahead);

        SyncEstimate {
            estimated_daa_lag,
            estimated_time_to_sync_seconds: self.estimate_time_to_sync_seconds(),
            reference_daa_score,
            reference_fetched_at: self.latest_reference_tip.as_ref().map(|tip| tip.fetched_at),
            reference_source: Some(config.reference_tip_source.clone()),
        }
    }

    fn reset(&mut self) {
        self.latest_reference_tip = None;
        self.previous_reference_tip = None;
        self.progress_history.clear();
    }

    fn should_refresh_reference(&self, now: DateTime<Utc>, config: &Config) -> bool {
        self.latest_reference_tip.as_ref().is_none_or(|tip| {
            now.signed_duration_since(tip.fetched_at)
                .to_std()
                .unwrap_or_default()
                >= config.reference_poll_interval
        })
    }

    async fn refresh_reference_tip(
        &mut self,
        reference_client: &HttpClient,
        config: &Config,
        now: DateTime<Utc>,
    ) -> Result<()> {
        let response = reference_client
            .get(&config.reference_tip_url)
            .send()
            .await
            .with_context(|| format!("failed to fetch {}", config.reference_tip_url))?
            .error_for_status()
            .with_context(|| {
                format!(
                    "reference API returned an error for {}",
                    config.reference_tip_url
                )
            })?;
        let payload = response
            .json::<ReferenceTipResponse>()
            .await
            .with_context(|| format!("failed to decode {}", config.reference_tip_url))?;

        let sample = ReferenceTipSample {
            virtual_daa_score: payload.virtual_daa_score,
            fetched_at: now,
        };
        self.previous_reference_tip = self.latest_reference_tip.replace(sample);
        Ok(())
    }

    fn estimated_reference_daa_score(&self, now: DateTime<Utc>, config: &Config) -> Option<u64> {
        let tip = self.latest_reference_tip.as_ref()?;
        let elapsed_seconds = now
            .signed_duration_since(tip.fetched_at)
            .num_milliseconds()
            .max(0) as f64
            / 1_000.0;
        let projected_seconds = elapsed_seconds.min(MAX_REFERENCE_EXTRAPOLATION_SECONDS);
        let projected_daa = (projected_seconds * self.reference_daa_rate(config)).round() as u64;

        Some(tip.virtual_daa_score.saturating_add(projected_daa))
    }

    fn reference_daa_rate(&self, config: &Config) -> f64 {
        self.previous_reference_tip
            .as_ref()
            .zip(self.latest_reference_tip.as_ref())
            .and_then(|(previous, latest)| {
                let elapsed_millis = latest
                    .fetched_at
                    .signed_duration_since(previous.fetched_at)
                    .num_milliseconds();
                let daa_delta = latest
                    .virtual_daa_score
                    .saturating_sub(previous.virtual_daa_score);

                (elapsed_millis > 0 && daa_delta > 0)
                    .then_some(daa_delta as f64 / (elapsed_millis as f64 / 1_000.0))
            })
            .unwrap_or(config.reference_daa_per_second)
    }

    fn record_progress(
        &mut self,
        now: DateTime<Utc>,
        estimated_daa_lag: Option<u64>,
        headers_ahead: u64,
    ) {
        self.progress_history.push_back(ProgressSample {
            observed_at: now,
            estimated_daa_lag,
            headers_ahead,
        });

        while self.progress_history.front().is_some_and(|sample| {
            now.signed_duration_since(sample.observed_at).num_seconds() > ETA_HISTORY_WINDOW_SECONDS
        }) {
            self.progress_history.pop_front();
        }
    }

    fn estimate_time_to_sync_seconds(&self) -> Option<u64> {
        let current = self.progress_history.back()?;
        let mut candidates = Vec::new();

        if let (Some(current_daa_lag), Some(rate)) = (
            current.estimated_daa_lag,
            self.progress_rate(current, |sample| sample.estimated_daa_lag),
        ) && current_daa_lag > 0
        {
            candidates.push((current_daa_lag as f64 / rate).ceil() as u64);
        }

        if let Some(rate) = self.progress_rate(current, |sample| Some(sample.headers_ahead))
            && current.headers_ahead > 0
        {
            candidates.push((current.headers_ahead as f64 / rate).ceil() as u64);
        }

        candidates.into_iter().max()
    }

    fn progress_rate(
        &self,
        current: &ProgressSample,
        selector: impl Fn(&ProgressSample) -> Option<u64>,
    ) -> Option<f64> {
        let current_value = selector(current)?;
        if current_value == 0 {
            return None;
        }

        self.progress_history.iter().find_map(|sample| {
            let elapsed_seconds = current
                .observed_at
                .signed_duration_since(sample.observed_at)
                .num_seconds();
            if elapsed_seconds < MIN_ETA_WINDOW_SECONDS {
                return None;
            }

            let previous_value = selector(sample)?;
            if previous_value <= current_value {
                return None;
            }

            Some((previous_value - current_value) as f64 / elapsed_seconds as f64)
        })
    }
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ReferenceTipResponse {
    #[serde(deserialize_with = "deserialize_u64")]
    virtual_daa_score: u64,
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

pub fn build_reference_client(config: &Config) -> Result<HttpClient> {
    HttpClient::builder()
        .timeout(config.request_timeout)
        .user_agent("kaspa-dashboard/0.1.0")
        .build()
        .context("failed to build reference tip client")
}

pub async fn refresh_loop(
    store: SnapshotStore,
    client: Arc<KaspaRpcClient>,
    reference_client: HttpClient,
    config: Config,
) {
    let mut estimator = SyncEstimator::new();

    loop {
        let previous = store.read().await;

        let next = if client.is_connected() {
            match fetch_snapshot(&client, &reference_client, &config, &mut estimator).await {
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
    reference_client: &HttpClient,
    config: &Config,
    estimator: &mut SyncEstimator,
) -> Result<DashboardSnapshot> {
    let info = call_with_timeout(&config.request_timeout, client.get_info())
        .await
        .context("getInfo failed")?;
    let server = call_with_timeout(&config.request_timeout, client.get_server_info())
        .await
        .context("getServerInfo failed")?;
    let blockdag = call_with_timeout(&config.request_timeout, client.get_block_dag_info())
        .await
        .context("getBlockDagInfo failed")?;
    let peers = call_with_timeout(&config.request_timeout, client.get_connected_peer_info())
        .await
        .context("getConnectedPeerInfo failed")?;

    let peers = map_peers(&peers.peer_info);
    let is_synced = server.is_synced || info.is_synced;
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
        is_synced,
        is_utxo_indexed: server.has_utxo_index || info.is_utxo_indexed,
        p2p_id: info.p2p_id.clone(),
    };
    let sync_estimate = estimator
        .update(reference_client, config, &kaspad, &blockdag)
        .await;

    let connection = ConnectionStatus {
        connected: true,
        state: "connected".to_string(),
        message: Some("Connected to kaspad over official wRPC".to_string()),
    };

    let sync_status =
        SyncStatus::from_snapshot(&connection, &kaspad, &blockdag, &sync_estimate, &peers);

    Ok(DashboardSnapshot {
        connection,
        kaspad,
        sync_status,
        blockdag,
        sync_estimate,
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
        &snapshot.sync_estimate,
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
        ping_sample_count: ping_count,
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

fn deserialize_u64<'de, D>(deserializer: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    match Value::deserialize(deserializer)? {
        Value::Number(value) => value
            .as_u64()
            .ok_or_else(|| de::Error::custom("expected an unsigned integer")),
        Value::String(value) => value
            .parse::<u64>()
            .map_err(|error| de::Error::custom(error.to_string())),
        other => Err(de::Error::custom(format!(
            "expected a string or number, got {other}"
        ))),
    }
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
    use std::time::Duration;

    use chrono::{Duration as ChronoDuration, TimeZone};

    use super::{ProgressSample, ReferenceTipSample, SyncEstimator, normalize_peer_version};
    use crate::config::Config;

    fn test_config() -> Config {
        Config {
            bind_addr: "127.0.0.1:3000".parse().unwrap(),
            static_dir: "../frontend/dist".into(),
            kaspad_wrpc_url: "ws://kaspad:17110".to_string(),
            refresh_interval: Duration::from_secs(3),
            request_timeout: Duration::from_secs(5),
            reference_tip_url: "https://api.kaspa.org/info/blockdag".to_string(),
            reference_tip_source: "api.kaspa.org".to_string(),
            reference_poll_interval: Duration::from_secs(900),
            reference_daa_per_second: 10.0,
        }
    }

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

    #[test]
    fn reference_rate_prefers_observed_remote_progress() {
        let config = test_config();
        let mut estimator = SyncEstimator::new();
        let start = chrono::Utc.with_ymd_and_hms(2026, 3, 23, 0, 0, 0).unwrap();

        estimator.previous_reference_tip = Some(ReferenceTipSample {
            virtual_daa_score: 100,
            fetched_at: start,
        });
        estimator.latest_reference_tip = Some(ReferenceTipSample {
            virtual_daa_score: 220,
            fetched_at: start + ChronoDuration::seconds(12),
        });

        assert_eq!(estimator.reference_daa_rate(&config), 10.0);
    }

    #[test]
    fn eta_uses_the_slower_of_daa_and_header_progress() {
        let mut estimator = SyncEstimator::new();
        let start = chrono::Utc.with_ymd_and_hms(2026, 3, 23, 0, 0, 0).unwrap();

        estimator.progress_history.push_back(ProgressSample {
            observed_at: start,
            estimated_daa_lag: Some(10_000),
            headers_ahead: 20_000,
        });
        estimator.progress_history.push_back(ProgressSample {
            observed_at: start + ChronoDuration::seconds(600),
            estimated_daa_lag: Some(4_000),
            headers_ahead: 14_000,
        });

        assert_eq!(estimator.estimate_time_to_sync_seconds(), Some(1_400));
    }
}
