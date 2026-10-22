import { defineConfig } from "@neon/config/v1";

export default defineConfig({
  // Declare your Neon services here
  auth: false,
  // AI Gateway requires a paid Neon plan. Re-enable once billing is upgraded:
  //   aiGateway: true,
  // Env vars (NEON_AI_GATEWAY_BASE_URL / NEON_AI_GATEWAY_TOKEN) are still pulled
  // and the app client reads them, so the gateway activates on upgrade with no code change.
  buckets: {
    // "private" is the default; use "public_read" for anonymous reads
    assets: { access: "private" },
  },
  // Branch policy: per-branch tuning
  branch: (branch) => {
    if (branch.isDefault) {
      // Default branch: no overrides, uses project defaults
      return {};
    }
    if (!branch.exists) {
      // New non-default branches: auto-expire
      // Run `neon checkout <name>` to create a new branch with these settings
      return { ttl: "7d" };
    }
    // Existing branch: no changes
    return {};
  },
});
