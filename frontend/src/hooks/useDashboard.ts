import { startTransition, useEffect, useEffectEvent, useState } from "react";
import { fetchDashboardSnapshot, type DashboardSnapshot } from "../api/dashboard";
import { getMockDashboardSnapshot, getRequestedMockScenario, type MockScenario } from "../api/mockDashboard";

export type DashboardRequestState = "loading" | "ready" | "refreshing" | "error";

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to refresh dashboard data";
}

export function useDashboard(refreshIntervalMs = 5000) {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [requestState, setRequestState] = useState<DashboardRequestState>("loading");
  const [requestError, setRequestError] = useState<string | null>(null);
  const [lastSuccessfulUpdate, setLastSuccessfulUpdate] = useState<string | null>(null);
  const mockScenario = getRequestedMockScenario(window.location.search);

  const refresh = useEffectEvent(async (signal: AbortSignal) => {
    setRequestState(snapshot ? "refreshing" : "loading");

    try {
      const nextSnapshot = await fetchDashboardSnapshot(signal);

      startTransition(() => {
        setSnapshot(nextSnapshot);
        setRequestState("ready");
        setRequestError(null);
        setLastSuccessfulUpdate(new Date().toISOString());
      });
    } catch (error) {
      if (signal.aborted) {
        return;
      }

      setRequestState("error");
      setRequestError(getErrorMessage(error));
    }
  });

  useEffect(() => {
    if (mockScenario) {
      const mockedSnapshot = getMockDashboardSnapshot(mockScenario);
      setSnapshot(mockedSnapshot);
      setRequestState("ready");
      setRequestError(null);
      setLastSuccessfulUpdate(mockedSnapshot.lastUpdate ?? new Date().toISOString());
      return;
    }

    let controller: AbortController | null = null;

    const runRefresh = async () => {
      controller?.abort();
      controller = new AbortController();
      await refresh(controller.signal);
    };

    void runRefresh();
    const interval = window.setInterval(() => {
      void runRefresh();
    }, refreshIntervalMs);

    return () => {
      window.clearInterval(interval);
      controller?.abort();
    };
  }, [refreshIntervalMs, mockScenario]);

  return {
    snapshot,
    requestState,
    requestError,
    lastSuccessfulUpdate,
    mockScenario,
  };
}
