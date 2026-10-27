// Accept the old CNA_<NAME> setting names for a while (rename step 3 of 4, owner order 2026-10-27).
//
// Every setting used to be called CNA_<NAME>; it is now NETWORK_ASSESSMENT_<NAME>. A deployment that still sets the old
// name keeps working: when the server starts, each old name whose new name has no value is copied to the new name. A new
// name that has a value always wins. A blank new name does not hide a non-blank old one, so a template that leaves the new
// name empty cannot switch off a protection that the old name still asks for. No value is ever logged or returned.
//
// This works in one direction only: an image built before this change reads only the old names, so while old and new
// images run side by side, and when rolling back, set both names to the same value.
//
// To end the fallback, delete this file, its test and the call in instrumentation.ts, and the Python side in
// network_assessment/_legacy_env.py.

const LEGACY_PREFIX = "CNA_";
const PREFIX = "NETWORK_ASSESSMENT_";

/** Copy each CNA_<NAME> to NETWORK_ASSESSMENT_<NAME> unless the new name already has a value. Returns the new names, sorted. */
export function adoptLegacyEnvironment(
  env: Record<string, string | undefined> = process.env,
): string[] {
  const adopted: string[] = [];
  for (const key of Object.keys(env).sort()) {
    if (!key.startsWith(LEGACY_PREFIX) || key.length === LEGACY_PREFIX.length) continue;
    const value = env[key];
    if (value === undefined) continue;
    const newName = PREFIX + key.slice(LEGACY_PREFIX.length);
    const current = env[newName];
    if (current) continue; // a new name that has a value always wins
    if (current === undefined || value) {
      // unset: copy the old value; blank: replace it only with a non-blank one
      env[newName] = value;
      adopted.push(newName);
    }
  }
  return adopted;
}
