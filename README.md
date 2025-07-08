# Kaspa Node Dashboard

A real-time web dashboard for monitoring your Kaspa node with detailed sync progress tracking.

## Quick Start

```bash
docker-compose up --build -d
```

Access dashboard at [http://localhost:4321](http://localhost:4321)

## Features

- **Real-time sync monitoring** - Live IBD progress with detailed phase tracking
- **Node metrics** - Block count, network stats, peer information
- **Responsive design** - Works on desktop and mobile

## Architecture

- **kaspad** - Kaspa node (rusty-kaspad)
- **api** - FastAPI backend with RPC communication  
- **frontend** - Nginx-served dashboard with live updates

## Ports

- `4321` - Dashboard (public)