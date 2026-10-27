// Accept the old CNA_<NAME> setting names for a while (rename step 3 of 4, owner order 2026-10-27).
//
// Every setting used to be called CNA_<NAME>; it is now NETWORK_ASSESSMENT_<NAME>. A deployment that still sets the old
// name keeps working: when the server starts, each old name whose new name is not set is copied to the new name. When
// both are set the new name wins, even if its value is empty. No value is ever logged or returned.
//
// To end the fallback, delete this file, its test and the call in instrumentation.ts, and the Python side in
// network_assessment/_legacy_env.py.

const LEGACY_PREFIX = "CNA_";
const PREFIX = "NETWORK_ASSESSMENT_";

/** Copy each CNA_<NAME> to NETWORK_ASSESSMENT_<NAME> when the new name is not set. Returns the new names, sorted. */
export function adoptLegacyEnvironment(
  env: Record<string, string | undefined> = process.env,
): string[] {
  const adopted: string[] = [];
  for (const key of Object.keys(env).sort()) {
    if (!key.startsWith(LEGACY_PREFIX) || key.length === LEGACY_PREFIX.length) continue;
    const value = env[key];
    if (value === undefined) continue;
    const newName = PREFIX + key.slice(LEGACY_PREFIX.length);
    if (env[newName] !== undefined) continue;
    env[newName] = value;
    adopted.push(newName);
  }
  return adopted;
}
