import promClient from "prom-client";
import { register } from "./middleware/metrics.js";

export const successfulSubmissions = new promClient.Counter({
  name: "multisig_successful_submissions_total",
  help: "Total successful multi-sig submissions",
  labelNames: ["asset"],
});
register.registerMetric(successfulSubmissions);

export const failedSubmissions = new promClient.Counter({
  name: "multisig_failed_submissions_total",
  help: "Total failed multi-sig submissions",
  labelNames: ["asset", "reason"],
});
register.registerMetric(failedSubmissions);

export const gasUsagePerAsset = new promClient.Histogram({
  name: "multisig_gas_usage_per_asset",
  help: "Gas usage per asset for multi-sig submissions",
  labelNames: ["asset"],
  buckets: [1000, 5000, 10000, 50000, 100000],
});
register.registerMetric(gasUsagePerAsset);

export const submissionDuration = new promClient.Histogram({
  name: "multisig_submission_duration_seconds",
  help: "Duration of multi-sig submission in seconds",
  labelNames: ["asset"],
  buckets: [0.1, 0.5, 1, 2, 5, 10],
});
register.registerMetric(submissionDuration);
