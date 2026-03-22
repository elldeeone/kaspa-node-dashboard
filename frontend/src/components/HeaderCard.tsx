import { useState } from "react";
import type { DashboardSnapshot } from "../api/dashboard";
import type { DashboardRequestState } from "../hooks/useDashboard";
import { copyToClipboard, formatNodeVersion } from "../lib/formatters";
import { InfoIcon } from "./icons";

type HeaderCardProps = {
  snapshot: DashboardSnapshot | null;
  requestState: DashboardRequestState;
};

function getConnectionState(snapshot: DashboardSnapshot | null, requestState: DashboardRequestState) {
  if (requestState === "error" && snapshot) {
    return {
      label: "Stale",
      indicatorClass: "bg-yellow-500 animate-pulse",
      title: "Dashboard is showing the last successful update",
    };
  }

  if (!snapshot) {
    return {
      label: "Connecting...",
      indicatorClass: "bg-gray-500 animate-pulse",
      title: "Waiting for initial dashboard data",
    };
  }

  if (snapshot.connection.connected && snapshot.connection.ready) {
    return {
      label: snapshot.connection.subscribed ? "Connected (Live)" : "Connected",
      indicatorClass: "bg-green-500",
      title: snapshot.connection.subscribed ? "WebSocket connected and subscribed" : "WebSocket connected and ready",
    };
  }

  if (snapshot.connection.connected) {
    return {
      label: "Initializing...",
      indicatorClass: "bg-yellow-500 animate-pulse",
      title: "WebSocket connected, initial state still loading",
    };
  }

  return {
    label: "Disconnected",
    indicatorClass: "bg-red-500 animate-pulse",
    title: "WebSocket disconnected, retrying",
  };
}

export function HeaderCard({ snapshot, requestState }: HeaderCardProps) {
  const [copied, setCopied] = useState(false);
  const connectionState = getConnectionState(snapshot, requestState);
  const p2pId = snapshot?.kaspad.p2pId || "Loading...";
  const status = !snapshot ? "Loading..." : snapshot.kaspad.isSynced ? "Running" : "Syncing";
  const statusClassName = !snapshot ? "text-zinc-300" : snapshot.kaspad.isSynced ? "text-teal-400" : "text-yellow-400";
  const uptime = snapshot?.kaspad.uptime.uptime_formatted;

  async function handleCopy() {
    if (!snapshot?.kaspad.p2pId) {
      return;
    }

    const didCopy = await copyToClipboard(snapshot.kaspad.p2pId);
    if (!didCopy) {
      return;
    }

    setCopied(true);
    window.setTimeout(() => setCopied(false), 1000);
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4 sm:p-6">
      <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <img alt="Kaspa Logo" className="h-[60px] w-[60px] flex-shrink-0" height="60" src="/kaspa-glow.png" width="60" />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold tracking-tight text-gray-50">Kaspa Node</h1>
            <p className="text-sm text-zinc-400">{snapshot ? formatNodeVersion(snapshot.kaspad.version) : "Loading..."}</p>
            <button
              aria-label="Copy P2P ID to clipboard"
              className="truncate text-left font-mono text-xs text-zinc-500"
              onClick={handleCopy}
              title={snapshot?.kaspad.p2pId ? `Click to copy P2P ID: ${snapshot.kaspad.p2pId}` : "P2P ID unavailable"}
              type="button"
            >
              {copied ? "P2P ID: Copied!" : `P2P ID: ${p2pId}`}
            </button>
            <div className="mt-2 flex items-center gap-2">
              <div className="flex items-center gap-1">
                <div className={`h-2 w-2 rounded-full ${connectionState.indicatorClass}`} title={connectionState.title} />
                <span className="text-xs text-zinc-400">{connectionState.label}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="w-full flex-shrink-0 text-center sm:w-auto sm:text-right">
          <div className="mb-1 flex items-center justify-center gap-2 sm:justify-end">
            <p className="text-sm text-zinc-400">Status</p>
            <div className="group relative">
              <InfoIcon aria-hidden="true" className="h-4 w-4 cursor-help text-zinc-500 hover:text-zinc-400" />
              <div className="status-help-tooltip pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 w-64 -translate-x-1/2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-center text-xs text-zinc-300 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                Please note that your node needs to fully synchronise with the Kaspa network before it can be used. Initial synchronisation may take at least 1-2 hours depending on your hardware and network connection.
              </div>
            </div>
          </div>
          <p className={`text-2xl font-bold ${statusClassName}`}>{status}</p>
          <p className="text-xs text-zinc-500">{uptime ? `for ${uptime}` : "Loading..."}</p>
        </div>
      </div>
    </div>
  );
}
