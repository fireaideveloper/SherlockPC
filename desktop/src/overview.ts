import type { Overview } from "./types";

// IPC replies can arrive out of order when a poll races with a manual capture.
export function newestOverview(
  current: Overview | null,
  incoming: Overview,
): Overview {
  return current &&
    current.storage?.generation === incoming.storage?.generation &&
    current.current.state_id > incoming.current.state_id
    ? current
    : incoming;
}
