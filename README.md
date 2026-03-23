# Kaspa Node Dashboard

A real-time dashboard for monitoring a local Rusty Kaspa node.

## Quick Start

```bash
docker-compose up --build -d
```

Access the dashboard at [http://localhost:4321](http://localhost:4321).

## What Changed

This branch is a hard cutover to a simpler runtime:

- `kaspad` runs as its own container
- `dashboard` is a Rust service that talks to `kaspad` over official wRPC
- the React frontend is built into the Rust service and served as static assets

There is no log scraping, no sync percentage heuristic, and no legacy Python API path.

## Features

- Live sync state based on official node RPC data
- BlockDAG and peer visibility from the local node
- Responsive frontend with built-in mock states for visual QA

## Services

- `kaspad` on the internal Docker network
- `dashboard` exposed publicly on port `4321`

## Development

- Frontend dev server: `cd frontend && npm run dev`
- Rust dashboard server: `cargo run --manifest-path dashboard/Cargo.toml`

The Vite dev server proxies `/api` requests to the Rust dashboard on `http://127.0.0.1:3000`.
