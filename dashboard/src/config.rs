use std::{env, net::SocketAddr, path::PathBuf, time::Duration};

use anyhow::{Context, Result};

#[derive(Debug, Clone)]
pub struct Config {
    pub bind_addr: SocketAddr,
    pub static_dir: PathBuf,
    pub kaspad_wrpc_url: String,
    pub refresh_interval: Duration,
    pub request_timeout: Duration,
    pub reference_tip_url: String,
    pub reference_tip_source: String,
    pub reference_poll_interval: Duration,
    pub reference_daa_per_second: f64,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let bind_addr = env::var("BIND_ADDR")
            .unwrap_or_else(|_| {
                format!(
                    "0.0.0.0:{}",
                    env::var("PORT").unwrap_or_else(|_| "3000".to_string())
                )
            })
            .parse()
            .context("failed to parse BIND_ADDR")?;

        let static_dir = env::var("STATIC_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("../frontend/dist"));

        let kaspad_wrpc_url =
            env::var("KASPAD_WRPC_URL").unwrap_or_else(|_| "ws://kaspad:17110".to_string());

        let refresh_interval = parse_duration_ms("REFRESH_INTERVAL_MS", 3_000)?;
        let request_timeout = parse_duration_ms("REQUEST_TIMEOUT_MS", 5_000)?;
        let reference_tip_url = env::var("REFERENCE_TIP_URL")
            .unwrap_or_else(|_| "https://api.kaspa.org/info/blockdag".to_string());
        let reference_tip_source =
            env::var("REFERENCE_TIP_SOURCE").unwrap_or_else(|_| "api.kaspa.org".to_string());
        let reference_poll_interval = parse_duration_ms("REFERENCE_POLL_INTERVAL_MS", 900_000)?;
        let reference_daa_per_second = parse_f64("REFERENCE_DAA_PER_SECOND", 10.0)?;

        Ok(Self {
            bind_addr,
            static_dir,
            kaspad_wrpc_url,
            refresh_interval,
            request_timeout,
            reference_tip_url,
            reference_tip_source,
            reference_poll_interval,
            reference_daa_per_second,
        })
    }
}

fn parse_duration_ms(key: &str, default_ms: u64) -> Result<Duration> {
    let value = env::var(key)
        .ok()
        .map(|raw| raw.parse::<u64>())
        .transpose()
        .with_context(|| format!("failed to parse {key} as milliseconds"))?
        .unwrap_or(default_ms);

    Ok(Duration::from_millis(value))
}

fn parse_f64(key: &str, default_value: f64) -> Result<f64> {
    env::var(key)
        .ok()
        .map(|raw| raw.parse::<f64>())
        .transpose()
        .with_context(|| format!("failed to parse {key} as a floating-point number"))?
        .map_or(Ok(default_value), Ok)
}
