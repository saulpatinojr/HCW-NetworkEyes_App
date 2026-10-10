/**
 * Image-update check — the I/O half of `image-update-rules.ts`.
 *
 * Reads the deployment's identity from the runtime environment contract the
 * appliance's Terraform injects, asks the registry what the newest build of
 * the same component is, and caches the answer in-process for the configured
 * interval. Every deployed appliance runs this on its own against the
 * registry it already pulls from, with the pull-only credential it already
 * holds; the core repository is never contacted.
 *
 * Runtime contract (all optional — a missing value degrades to "unknown",
 * never to a false "up to date"):
 *   CNA_BUILD_SHA                          commit the image was built from (baked at build time)
 *   CNA_WEB_IMAGE                          image reference Terraform deployed (repository + tag)
 *   CNA_IMAGE_REGISTRY_USERNAME            pull-only registry credential
 *   CNA_IMAGE_REGISTRY_TOKEN               pull-only registry credential (secret)
 *   CNA_IMAGE_UPDATE_CHECK_INTERVAL_MINUTES  cache interval; 0 disables the check
 *   CNA_APPLIANCE_REPO                     owner/repo of the appliance that deployed this instance
 *   CNA_GITHUB_SERVER_URL                  GitHub base URL (GHES), default https://github.com
 */

import {
  applianceLinks,
  clean,
  compareBuilds,
  componentOfTag,
  distributionApiHost,
  floatingTagFor,
  isImageIndex,
  LABEL_CREATED,
  LABEL_REVISION,
  MANIFEST_ACCEPT_TYPES,
  type OciImageConfig,
  type OciIndex,
  type OciManifest,
  parseBearerChallenge,
  parseImageReference,
  parseIntervalMinutes,
  pullScopeFor,
  selectPlatformManifest,
  shaOfTag,
  shaTagFor,
  shortSha,
  tokenUrlFor,
  type UpdateVerdict,
} from "./image-update-rules";

export type { UpdateVerdict };

/** How long a registry answer is reused before the next check. */
export const DEFAULT_CHECK_INTERVAL_MINUTES = 60;
/** Per-request timeout; the registry is a small, fast dependency. */
export const REGISTRY_REQUEST_TIMEOUT_MS = 10_000;
/** Public GitHub; overridable for GitHub Enterprise Server deployments. */
export const DEFAULT_GITHUB_SERVER_URL = "https://github.com";

export type ImageUpdateState = {
  /** False when the check is switched off or the deployment has no image reference. */
  enabled: boolean;
  intervalMinutes: number;
  running: {
    /** Full commit SHA the image was built from, when baked in. */
    buildSha: string;
    /** Immutable tag the running build corresponds to (`web-sha-<7>`), when derivable. */
    shaTag: string;
    /** The reference Terraform deployed, as recorded in the environment. */
    image: string;
  };
  published: {
    /** Floating tag that was resolved (`web-latest`). */
    floatingTag: string;
    /** Commit SHA of the newest published build. */
    revision: string;
    /** Immutable tag of that build (`web-sha-<7>`). */
    shaTag: string;
    /** Build timestamp from the image labels. */
    createdAt: string;
  };
  verdict: UpdateVerdict;
  /** When the registry was last consulted (ISO); empty before the first check. */
  checkedAt: string;
  /** Why the verdict is unknown, when it is. */
  error: string;
  /** Whether this answer came from the registry or from the in-process cache. */
  source: "registry" | "cache" | "disabled";
  appliance: ReturnType<typeof applianceLinks>;
};

type Cached = { state: ImageUpdateState; expiresAt: number };

let cache: Cached | null = null;

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

export function getRunningBuildSha(): string {
  return clean(process.env.CNA_BUILD_SHA).toLowerCase();
}

export function getDeployedWebImage(): string {
  return clean(process.env.CNA_WEB_IMAGE);
}

export function getCheckIntervalMinutes(): number {
  return parseIntervalMinutes(
    process.env.CNA_IMAGE_UPDATE_CHECK_INTERVAL_MINUTES,
    DEFAULT_CHECK_INTERVAL_MINUTES,
  );
}

function registryCredentials(): { username: string; token: string } | null {
  const username = clean(process.env.CNA_IMAGE_REGISTRY_USERNAME);
  const token = clean(process.env.CNA_IMAGE_REGISTRY_TOKEN);
  return username && token ? { username, token } : null;
}

function applianceLinksFromEnv() {
  return applianceLinks(
    process.env.CNA_APPLIANCE_REPO,
    clean(process.env.CNA_GITHUB_SERVER_URL) || DEFAULT_GITHUB_SERVER_URL,
  );
}

// ---------------------------------------------------------------------------
// Registry client (OCI distribution API, bearer-token auth)
// ---------------------------------------------------------------------------

class RegistryError extends Error {}

async function registryFetch(
  url: string,
  init: RequestInit,
  auth: { bearer: string | null; basic: string | null; scope: string },
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (auth.bearer) headers.set("Authorization", `Bearer ${auth.bearer}`);

  const first = await fetch(url, { ...init, headers, signal: AbortSignal.timeout(REGISTRY_REQUEST_TIMEOUT_MS) });
  if (first.status !== 401 || auth.bearer) return first;

  // Standard token dance: the registry names its token endpoint in the
  // challenge; we ask it for a pull-scoped token with the pull credential
  // (or anonymously for a public repository) and retry once.
  const challenge = parseBearerChallenge(first.headers.get("www-authenticate"));
  if (!challenge) throw new RegistryError("Registry requires authentication but sent no bearer challenge.");

  const tokenHeaders = new Headers();
  if (auth.basic) tokenHeaders.set("Authorization", `Basic ${auth.basic}`);
  const tokenResponse = await fetch(tokenUrlFor(challenge, auth.scope), {
    headers: tokenHeaders,
    signal: AbortSignal.timeout(REGISTRY_REQUEST_TIMEOUT_MS),
  });
  if (!tokenResponse.ok) {
    throw new RegistryError(
      auth.basic
        ? `Registry rejected the pull credential (HTTP ${tokenResponse.status}).`
        : `Registry requires a pull credential (HTTP ${tokenResponse.status}); set CNA_IMAGE_REGISTRY_USERNAME/TOKEN.`,
    );
  }
  const tokenBody = (await tokenResponse.json()) as { token?: string; access_token?: string };
  const bearer = tokenBody.token || tokenBody.access_token || "";
  if (!bearer) throw new RegistryError("Registry token endpoint returned no token.");
  auth.bearer = bearer;

  headers.set("Authorization", `Bearer ${bearer}`);
  return fetch(url, { ...init, headers, signal: AbortSignal.timeout(REGISTRY_REQUEST_TIMEOUT_MS) });
}

async function readJson<T>(response: Response, what: string): Promise<T> {
  if (!response.ok) throw new RegistryError(`Registry returned HTTP ${response.status} for ${what}.`);
  return (await response.json()) as T;
}

/**
 * Resolve the newest published build of the component behind `image`:
 * `<repo>:<component>-latest` → (index → platform manifest) → config labels.
 */
export async function fetchPublishedBuild(image: string): Promise<{
  floatingTag: string;
  revision: string;
  createdAt: string;
}> {
  const ref = parseImageReference(image);
  if (!ref) throw new RegistryError(`CNA_WEB_IMAGE is not a valid image reference: "${image}".`);

  const floatingTag = floatingTagFor(ref.tag);
  const base = `https://${distributionApiHost(ref.registry)}/v2/${ref.repository}`;
  const creds = registryCredentials();
  const auth = {
    bearer: null as string | null,
    basic: creds ? Buffer.from(`${creds.username}:${creds.token}`).toString("base64") : null,
    scope: pullScopeFor(ref.repository),
  };
  const manifestInit: RequestInit = { headers: { Accept: MANIFEST_ACCEPT_TYPES.join(", ") } };

  let manifest = await readJson<OciIndex | OciManifest>(
    await registryFetch(`${base}/manifests/${floatingTag}`, manifestInit, auth),
    `tag ${floatingTag}`,
  );

  if (isImageIndex(manifest)) {
    const platform = selectPlatformManifest(manifest);
    if (!platform) throw new RegistryError(`Tag ${floatingTag} carries no runnable image manifest.`);
    manifest = await readJson<OciManifest>(
      await registryFetch(`${base}/manifests/${platform.digest}`, manifestInit, auth),
      `manifest ${platform.digest}`,
    );
  }

  const configDigest = (manifest as OciManifest).config?.digest;
  if (!configDigest) throw new RegistryError(`Manifest for ${floatingTag} has no config descriptor.`);

  const config = await readJson<OciImageConfig>(
    await registryFetch(`${base}/blobs/${configDigest}`, {}, auth),
    `config ${configDigest}`,
  );
  const labels = config.config?.Labels ?? {};
  const revision = clean(labels[LABEL_REVISION]).toLowerCase();
  if (!shortSha(revision)) {
    throw new RegistryError(`Image ${floatingTag} carries no ${LABEL_REVISION} label.`);
  }
  return { floatingTag, revision, createdAt: clean(labels[LABEL_CREATED]) || clean(config.created) };
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

function baseState(): ImageUpdateState {
  const image = getDeployedWebImage();
  const buildSha = getRunningBuildSha();
  const ref = parseImageReference(image);
  const component = ref ? componentOfTag(ref.tag) : "web";
  // The baked build SHA is authoritative (220-fast-redeploy swaps images
  // without touching env); the deployed tag is the fallback for older images.
  const runningShort = shortSha(buildSha) || (ref ? shaOfTag(ref.tag) : "");
  return {
    enabled: false,
    intervalMinutes: getCheckIntervalMinutes(),
    running: {
      buildSha,
      shaTag: runningShort ? shaTagFor(component, runningShort) : "",
      image,
    },
    published: { floatingTag: ref ? floatingTagFor(ref.tag) : "", revision: "", shaTag: "", createdAt: "" },
    verdict: "unknown",
    checkedAt: "",
    error: "",
    source: "disabled",
    appliance: applianceLinksFromEnv(),
  };
}

/**
 * The deployment's update state. Cached for the configured interval;
 * `force` (the admin's "Check now") bypasses the cache. Never throws: a
 * registry problem is reported in `error` with an "unknown" verdict.
 */
export async function getImageUpdateState(options: { force?: boolean } = {}): Promise<ImageUpdateState> {
  const state = baseState();
  if (state.intervalMinutes === 0) {
    state.error = "Update check is switched off (CNA_IMAGE_UPDATE_CHECK_INTERVAL_MINUTES=0).";
    return state;
  }
  if (!state.running.image) {
    state.error = "CNA_WEB_IMAGE is not set; the deployment does not know which image it runs.";
    return state;
  }
  state.enabled = true;

  const now = Date.now();
  if (!options.force && cache && cache.expiresAt > now) {
    return { ...cache.state, source: "cache", appliance: state.appliance };
  }

  try {
    const published = await fetchPublishedBuild(state.running.image);
    const component = componentOfTag(published.floatingTag);
    state.published = {
      floatingTag: published.floatingTag,
      revision: published.revision,
      shaTag: shaTagFor(component, published.revision),
      createdAt: published.createdAt,
    };
    const runningShort = state.running.buildSha || shaOfTag(parseImageReference(state.running.image)?.tag ?? "");
    state.verdict = compareBuilds(runningShort, published.revision);
    if (state.verdict === "unknown") {
      state.error = "The running build is unknown (CNA_BUILD_SHA is not set and the deployed tag carries no SHA).";
    }
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  }
  state.checkedAt = new Date(now).toISOString();
  state.source = "registry";
  cache = { state, expiresAt: now + state.intervalMinutes * 60_000 };
  return state;
}

/** Test seam. */
export function resetImageUpdateCache(): void {
  cache = null;
}
