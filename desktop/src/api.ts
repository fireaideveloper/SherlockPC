import { invoke } from "@tauri-apps/api/core";
import type {
  Investigation,
  Overview,
  StorageInfo,
  HistoryPage,
} from "./types";

type BackendEnvelope<T> = {
  ok: boolean;
  result?: T;
  error?: string;
};

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return "Unknown local backend error";
  }
}

async function callBackend<T>(payload: Record<string, unknown>): Promise<T> {
  try {
    const response = await invoke<BackendEnvelope<T>>("backend_call", {
      payload,
    });
    if (!response.ok || response.result === undefined) {
      throw new Error(response.error || "Sherlock backend returned no result");
    }
    return response.result;
  } catch (error) {
    const message = errorMessage(error);
    if (
      message.toLowerCase().includes("sidecar") ||
      message.toLowerCase().includes("backend")
    ) {
      throw new Error(`Local Sherlock core failed to start: ${message}`);
    }
    throw new Error(message);
  }
}

export async function loadOverview(): Promise<{
  overview: Overview | null;
  error: string | null;
}> {
  const response =
    await invoke<
      BackendEnvelope<{ overview: Overview | null; error: string | null }>
    >("monitor_status");
  if (!response.ok || !response.result)
    throw new Error(response.error || "Monitor unavailable");
  return response.result;
}

export function runInvestigation(question: string): Promise<Investigation> {
  return callBackend<Investigation>({
    action: "investigate",
    question,
  });
}

export function refreshState(): Promise<Overview> {
  return invoke<Overview>("refresh_state");
}

export type StartupStatus = {
  supported: boolean;
  enabled: boolean;
  error: string | null;
};

export function loadStartupStatus(): Promise<StartupStatus> {
  return invoke<StartupStatus>("startup_status");
}

export function setStartupEnabled(enabled: boolean): Promise<StartupStatus> {
  return invoke<StartupStatus>("set_startup_enabled", { enabled });
}

export const loadStorageInfo = () =>
  callBackend<StorageInfo>({ action: "history_info" });
export const openHistoryFolder = () =>
  callBackend<StorageInfo>({ action: "open_history_folder" });
export const clearHistory = () =>
  callBackend<{ deleted_count: number; storage: StorageInfo }>({
    action: "clear_history",
    confirmed: true,
  });
export const loadHistoryPage = (
  page: number,
  pageSize: number,
  anchorId: number | null = null,
) =>
  callBackend<HistoryPage>({
    action: "history_page",
    page,
    page_size: pageSize,
    anchor_id: anchorId,
  });

export const setNativeLocale = (locale: string) =>
  invoke<void>("set_locale", { locale });
