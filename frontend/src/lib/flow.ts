import { api } from "./api";
import type { Dataset, Product, RunSummary } from "./types";

export type PublicConfig = {
  default_run_budget_usd: number;
  max_run_budget_usd: number;
  models: { triage: string; agent: string; embedding: string };
};

let configCache: Promise<PublicConfig> | null = null;
export const getConfig = () => (configCache ??= api.get<PublicConfig>("/api/config"));

export const BUDGET_OPTIONS = [0.05, 0.1, 0.25, 0.5, 1.0];

/** One click: sample product (prebuilt profile) + sample chat + default budget -> a run id. */
export async function startSampleRun(productKey = "pystart"): Promise<number> {
  const [product, dataset, cfg] = await Promise.all([
    api.post<Product>(`/api/products/sample/${productKey}`),
    api.get<Dataset>("/api/datasets/sample"),
    getConfig(),
  ]);
  const run = await api.post<RunSummary>("/api/runs", {
    product_id: product.id, dataset_id: dataset.id, budget_usd: cfg.default_run_budget_usd,
  });
  return run.id;
}
