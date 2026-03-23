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

  if (snapshot.connection.connected) {
    return {
      label: "Connected",
      indicatorClass: "bg-green-500",
      title: snapshot.connection.message ?? "Connected to kaspad",
    };
  }

  return {
    label: "Disconnected",
    indicatorClass: "bg-red-500 animate-pulse",
    title: "Dashboard is retrying its connection to kaspad",
  };
}

export function HeaderCard({ snapshot, requestState }: HeaderCardProps) {
  const [copied, setCopied] = useState(false);
  const [statusHelpVisible, setStatusHelpVisible] = useState(false);
  const connectionState = getConnectionState(snapshot, requestState);
  const p2pId = snapshot?.kaspad.p2pId || "Loading...";
  const status = !snapshot ? "Loading..." : snapshot.kaspad.isSynced ? "Running" : snapshot.syncStatus.label;
  const statusClassName = !snapshot ? "text-zinc-300" : snapshot.kaspad.isSynced ? "text-teal-400" : "text-yellow-400";
  const network = snapshot?.kaspad.network;

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
        <div className="flex min-w-0 w-full flex-col items-start gap-3 sm:w-auto sm:flex-1 sm:flex-row sm:items-center sm:gap-4">
          <img alt="Kaspa Logo" className="h-[60px] w-[60px] flex-shrink-0" height="60" src="/kaspa-glow.png" width="60" />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-bold tracking-tight text-gray-50">Kaspa Node</h1>
            <p className="text-sm text-zinc-400">{snapshot ? formatNodeVersion(snapshot.kaspad.version) : "Loading..."}</p>
            <button
              aria-label="Copy P2P ID to clipboard"
              className="block w-full max-w-full truncate text-left font-mono text-xs text-zinc-500"
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
            <div
              className="relative"
              onMouseEnter={() => setStatusHelpVisible(true)}
              onMouseLeave={() => setStatusHelpVisible(false)}
            >
              <button
                aria-describedby="status-help-tooltip"
                aria-expanded={statusHelpVisible}
                aria-label="Show status help"
                className="rounded-full p-0.5 text-zinc-500 outline-none transition-colors hover:text-zinc-400 focus-visible:ring-2 focus-visible:ring-teal-400/70"
                onBlur={() => setStatusHelpVisible(false)}
                onClick={() => setStatusHelpVisible((visible) => !visible)}
                onFocus={() => setStatusHelpVisible(true)}
                type="button"
              >
                <InfoIcon aria-hidden="true" className="h-4 w-4 cursor-help" />
              </button>
              <div
                className={`status-help-tooltip pointer-events-none absolute right-0 top-full z-10 mt-2 w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-left text-xs text-zinc-300 transition-opacity duration-200 ${
                  statusHelpVisible ? "opacity-100" : "opacity-0"
                }`}
                id="status-help-tooltip"
              >
                Please note that your node needs to fully synchronise with the Kaspa network before it can be used. Initial synchronisation may take at least 1-2 hours depending on your hardware and network connection.
              </div>
            </div>
          </div>
          <p className={`text-2xl font-bold ${statusClassName}`}>{status}</p>
          <p className="text-xs text-zinc-500">{network ? `Network: ${network}` : "Loading..."}</p>
        </div>
      </div>
    </div>
  );
}
