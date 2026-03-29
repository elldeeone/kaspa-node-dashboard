mod config;
mod models;
mod service;

use std::path::PathBuf;

use anyhow::Result;
use axum::{
    Json, Router,
    extract::State,
    response::IntoResponse,
    routing::{get, get_service},
};
use tokio::net::TcpListener;
use tower_http::{
    services::{ServeDir, ServeFile},
    trace::TraceLayer,
};
use tracing::info;

use crate::{config::Config, models::DashboardSnapshot, service::SnapshotStore};

#[derive(Clone)]
struct AppState {
    snapshots: SnapshotStore,
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{SignalKind, signal};

        let mut terminate = signal(SignalKind::terminate()).expect("failed to install SIGTERM handler");
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {}
            _ = terminate.recv() => {}
        }
    }

    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "kaspa_dashboard=info,tower_http=info".into()),
        )
        .init();

    let config = Config::from_env()?;
    let snapshots = SnapshotStore::new(DashboardSnapshot::default());
    let client = service::connect_client(&config).await?;
    let reference_client = service::build_reference_client(&config)?;

    let refresh_store = snapshots.clone();
    let refresh_config = config.clone();
    tokio::spawn(async move {
        service::refresh_loop(refresh_store, client, reference_client, refresh_config).await;
    });

    let router = build_router(
        AppState {
            snapshots: snapshots.clone(),
        },
        config.static_dir.clone(),
    );

    let listener = TcpListener::bind(config.bind_addr).await?;
    info!("dashboard listening on {}", config.bind_addr);

    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    Ok(())
}

fn build_router(state: AppState, static_dir: PathBuf) -> Router {
    let index_file = static_dir.join("index.html");
    let static_files = get_service(
        ServeDir::new(static_dir.clone()).not_found_service(ServeFile::new(index_file)),
    );

    Router::new()
        .route("/api/dashboard", get(get_dashboard))
        .route("/health", get(health))
        .fallback_service(static_files)
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

async fn get_dashboard(State(state): State<AppState>) -> Json<DashboardSnapshot> {
    Json(state.snapshots.read().await)
}

async fn health() -> impl IntoResponse {
    "ok"
}
