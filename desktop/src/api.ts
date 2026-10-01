import { invoke } from "@tauri-apps/api/core";
import type { Investigation, Overview } from "./types";

type BackendEnvelope<T> = {
  ok: boolean;
  result?: T;
  error?: string;
};

async function callBackend<T>(payload: Record<string, unknown>): Promise<T> {
  const response = await invoke<BackendEnvelope<T>>("backend_call", { payload });
  if (!response.ok || response.result === undefined) {
    throw new Error(response.error || "Sherlock backend returned no result");
  }
  return response.result;
}

export function loadOverview(): Promise<Overview> {
  return callBackend<Overview>({ action: "overview" });
}

export function runInvestigation(question: string): Promise<Investigation> {
  return callBackend<Investigation>({
    action: "investigate",
    question,
  });
}
