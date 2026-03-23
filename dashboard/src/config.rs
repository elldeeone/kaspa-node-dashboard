use std::{env, net::SocketAddr, path::PathBuf, time::Duration};

use anyhow::{Context, Result};

#[derive(Debug, Clone)]
pub struct Config {
    pub bind_addr: SocketAddr,
    pub static_dir: PathBuf,
    pub kaspad_wrpc_url: String,
    pub refresh_interval: Duration,
    pub request_timeout: Duration,
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

        Ok(Self {
            bind_addr,
            static_dir,
            kaspad_wrpc_url,
            refresh_interval,
            request_timeout,
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
