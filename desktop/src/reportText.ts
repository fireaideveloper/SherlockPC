import { t } from "./i18n";

// Localize presentation only. Canonical evidence text and IDs remain untouched.
export function reportText(text: string): string {
  const direct = t(text);
  if (direct !== text) return direct;
  let match = text.match(/^Check system deviations for state (\d+)\.$/);
  if (match) return t("traceUnderstand", { id: match[1] });
  match = text.match(
    /^One read, up to (\d+) historical states; CPU\/RAM\/swap rules\.$/,
  );
  if (match) return t("tracePlan", { count: match[1] });
  match = text.match(
    /^(cpu_percent|memory_percent|swap_percent) is (above|below) the historical P10-P90 range beyond the tolerance\.$/,
  );
  if (match)
    return t(match[2] === "above" ? "deviationAbove" : "deviationBelow", {
      metric: t(match[1]),
    });
  match = text.match(
    /^Observed (cpu_percent|memory_percent|swap_percent) >= ([\d.]+)%; the signal is supported, its causal role is not\.$/,
  );
  if (match)
    return t("supportedRule", { metric: t(match[1]), threshold: match[2] });
  match = text.match(
    /^Relative deviation does not meet the (cpu_percent|memory_percent|swap_percent) >= ([\d.]+)% signal rule\.$/,
  );
  if (match)
    return t("insufficientRule", { metric: t(match[1]), threshold: match[2] });
  return direct;
}
