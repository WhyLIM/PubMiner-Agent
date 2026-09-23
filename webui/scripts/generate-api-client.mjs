/**
 * Regenerate the typed API client contract from the PubMiner backend.
 *
 * Usage:
 *   1) Start the backend (PubMiner repo): `uvicorn pubminer.api.app:create_app --factory --port 8001`
 *   2) `pnpm gen:api`  — fetches /openapi.json and regenerates src/shared/api/schema.d.ts.
 *
 * Without a running backend the committed src/shared/api/openapi.json is used.
 */
import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const BASE_URL = process.env.AGENT_API_URL ?? "http://localhost:8001";
const SPEC_PATH = resolve("src/shared/api/openapi.json");
const OUT_PATH = resolve("src/shared/api/schema.d.ts");

async function fetchSpec() {
  try {
    const response = await fetch(`${BASE_URL}/openapi.json`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn(`[gen:api] backend unreachable (${error.message}); using committed openapi.json`);
    return null;
  }
}

const spec = await fetchSpec();
if (spec) {
  writeFileSync(SPEC_PATH, JSON.stringify(spec, null, 2) + "\n");
  console.log("[gen:api] refreshed openapi.json from", BASE_URL);
}
execSync(`pnpm exec openapi-typescript ${SPEC_PATH} -o ${OUT_PATH}`, { stdio: "inherit" });
console.log("[gen:api] wrote", OUT_PATH);
