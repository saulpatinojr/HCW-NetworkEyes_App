/**
 * Image-update rules — pure functions, no I/O.
 *
 * A deployed appliance runs immutable images (`cna:{web,api,worker}-sha-<7>`)
 * and only changes them through its own workflows: `230-image-update` picks
 * up every new image set the core publishes, redeploys `dev` automatically
 * and opens an `update-available` issue for `prod`, which a human applies via
 * `210-deploy`. Nothing inside the containers updates itself.
 *
 * This module gives the web tier a way to *see* that state per deployment:
 * the running build (baked into the image as CNA_BUILD_SHA at build time) is
 * compared with the newest build the registry carries under the floating
 * `*-latest` tag of the same component. The comparison is registry-agnostic
 * (OCI distribution API) and every deployed appliance checks on its own with
 * the pull-only credential it already holds — no shared service and no access
 * to the core repository is involved.
 *
 * Everything that reads the environment or the network lives in
 * `image-update.ts`; this file holds the rules so they can be unit-tested.
 */

/** Floating-tag suffix of the contract (`web-latest`, `api-latest`, `latest`). */
export const FLOATING_TAG_SUFFIX = "latest";
/** Immutable-tag marker of the contract (`web-sha-<7>`, `sha-<7>`). */
export const SHA_TAG_MARKER = "sha-";
/** Length of the short commit SHA the tag scheme uses. */
export const SHORT_SHA_LENGTH = 7;

/** Registry host Docker Hub image references resolve to. */
export const DOCKER_HUB_REGISTRY = "docker.io";
/** The OCI distribution API host for Docker Hub references. */
export const DOCKER_HUB_API_HOST = "registry-1.docker.io";
/** Docker Hub's library namespace for bare references (`postgres` → `library/postgres`). */
export const DOCKER_HUB_LIBRARY_NAMESPACE = "library";

/** OCI labels `docker/metadata-action` stamps on every image the core builds. */
export const LABEL_REVISION = "org.opencontainers.image.revision";
export const LABEL_CREATED = "org.opencontainers.image.created";

/** Manifest media types the registry client accepts, in preference order. */
export const MANIFEST_ACCEPT_TYPES = [
  "application/vnd.oci.image.index.v1+json",
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.oci.image.manifest.v1+json",
  "application/vnd.docker.distribution.manifest.v2+json",
] as const;

/** Buildx marks provenance/SBOM attestations with this annotation. */
export const ATTESTATION_ANNOTATION = "vnd.docker.reference.type";
export const ATTESTATION_ANNOTATION_VALUE = "attestation-manifest";

/** The platform the appliances run; attestation manifests report `unknown`. */
export const TARGET_PLATFORM = { os: "linux", architecture: "amd64" } as const;

/**
 * Appliance workflow files the page links to. Numbers and names are part of
 * the shared contract (CLAUDE.md → workflow bands) and never change.
 */
export const APPLIANCE_IMAGE_UPDATE_WORKFLOW = "230-image-update.yml";
export const APPLIANCE_DEPLOY_WORKFLOW = "210-deploy.yml";
/** Label `230-image-update` puts on the prod update request it opens. */
export const APPLIANCE_UPDATE_ISSUE_LABEL = "update-available";

export type ImageReference = {
  /** Registry host, e.g. `docker.io` or `ghcr.io`. */
  registry: string;
  /** Repository path under the registry, e.g. `acme/cna`. */
  repository: string;
  /** Tag; empty when the reference pins a digest instead. */
  tag: string;
  /** Digest when the reference is `repo@sha256:...`; otherwise empty. */
  digest: string;
};

export type UpdateVerdict = "up-to-date" | "update-available" | "unknown";

export type OciDescriptor = {
  mediaType?: string;
  digest: string;
  size?: number;
  platform?: { os?: string; architecture?: string; variant?: string };
  annotations?: Record<string, string>;
};

export type OciIndex = {
  schemaVersion?: number;
  mediaType?: string;
  manifests?: OciDescriptor[];
};

export type OciManifest = {
  schemaVersion?: number;
  mediaType?: string;
  config?: OciDescriptor;
  layers?: OciDescriptor[];
};

export type OciImageConfig = {
  config?: { Labels?: Record<string, string> };
  created?: string;
};

export type BearerChallenge = {
  realm: string;
  service?: string;
  scope?: string;
};

export function clean(value: string | undefined | null): string {
  return (value ?? "").trim();
}

/**
 * Parse `[registry/]repository[:tag][@digest]`. Docker Hub conventions apply:
 * no registry → `docker.io`; a single path segment → `library/<name>`;
 * no tag and no digest → `latest`.
 */
export function parseImageReference(raw: string | undefined | null): ImageReference | null {
  const value = clean(raw);
  if (!value || /\s/.test(value)) return null;

  let rest = value;
  let digest = "";
  const at = rest.indexOf("@");
  if (at >= 0) {
    digest = rest.slice(at + 1);
    rest = rest.slice(0, at);
    if (!/^sha256:[0-9a-f]{64}$/i.test(digest)) return null;
  }

  // A registry host is the first segment when it contains a dot or a colon
  // (port) or is `localhost`; otherwise the whole thing is a Docker Hub path.
  const segments = rest.split("/");
  let registry = DOCKER_HUB_REGISTRY;
  if (segments.length > 1) {
    const first = segments[0];
    if (first.includes(".") || first.includes(":") || first === "localhost") {
      registry = first;
      segments.shift();
    }
  }

  let path = segments.join("/");
  let tag = "";
  const lastSlash = path.lastIndexOf("/");
  const colon = path.lastIndexOf(":");
  if (colon > lastSlash) {
    tag = path.slice(colon + 1);
    path = path.slice(0, colon);
  }
  if (!path) return null;
  if (!tag && !digest) tag = FLOATING_TAG_SUFFIX;
  if (tag && !/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/.test(tag)) return null;

  if (registry === DOCKER_HUB_REGISTRY && !path.includes("/")) {
    path = `${DOCKER_HUB_LIBRARY_NAMESPACE}/${path}`;
  }

  return { registry, repository: path, tag, digest };
}

/** `web-sha-abc1234` → `web`, `api-latest` → `api`, `sha-abc1234` / `latest` → `` */
export function componentOfTag(tag: string): string {
  const value = clean(tag);
  if (value.startsWith(SHA_TAG_MARKER) || value === FLOATING_TAG_SUFFIX) return "";
  const shaAt = value.indexOf(`-${SHA_TAG_MARKER}`);
  if (shaAt > 0) return value.slice(0, shaAt);
  const latestAt = value.lastIndexOf(`-${FLOATING_TAG_SUFFIX}`);
  if (latestAt > 0 && latestAt === value.length - FLOATING_TAG_SUFFIX.length - 1) {
    return value.slice(0, latestAt);
  }
  return "";
}

/** The floating tag that tracks the newest build of the same component. */
export function floatingTagFor(tag: string): string {
  const component = componentOfTag(tag);
  return component ? `${component}-${FLOATING_TAG_SUFFIX}` : FLOATING_TAG_SUFFIX;
}

/** The immutable tag the contract gives a build of `component` at `revision`. */
export function shaTagFor(component: string, revision: string): string {
  const short = shortSha(revision);
  if (!short) return "";
  return component ? `${component}-${SHA_TAG_MARKER}${short}` : `${SHA_TAG_MARKER}${short}`;
}

/** First 7 hex characters, lower-cased; empty when the input is not a SHA. */
export function shortSha(revision: string | undefined | null): string {
  const value = clean(revision).toLowerCase();
  if (!/^[0-9a-f]{7,40}$/.test(value)) return "";
  return value.slice(0, SHORT_SHA_LENGTH);
}

/** Short SHA carried by an immutable tag (`web-sha-abc1234` → `abc1234`). */
export function shaOfTag(tag: string): string {
  const value = clean(tag);
  const at = value.lastIndexOf(SHA_TAG_MARKER);
  if (at < 0) return "";
  return shortSha(value.slice(at + SHA_TAG_MARKER.length));
}

/**
 * The verdict compares short SHAs because the tag scheme carries 7
 * characters; either side missing means the answer is unknown, never a
 * false "up to date".
 */
export function compareBuilds(
  running: string | undefined | null,
  published: string | undefined | null,
): UpdateVerdict {
  const a = shortSha(running);
  const b = shortSha(published);
  if (!a || !b) return "unknown";
  return a === b ? "up-to-date" : "update-available";
}

/** True for buildx provenance/SBOM attestation entries in an image index. */
export function isAttestationManifest(descriptor: OciDescriptor): boolean {
  if (descriptor.annotations?.[ATTESTATION_ANNOTATION] === ATTESTATION_ANNOTATION_VALUE) return true;
  return descriptor.platform?.os === "unknown" || descriptor.platform?.architecture === "unknown";
}

/**
 * Pick the runnable manifest for the target platform out of an image index.
 * Falls back to the first non-attestation entry so a single-platform index
 * built for another architecture still resolves to *something* honest.
 */
export function selectPlatformManifest(
  index: OciIndex,
  platform: { os: string; architecture: string } = TARGET_PLATFORM,
): OciDescriptor | null {
  const candidates = (index.manifests ?? []).filter((m) => m.digest && !isAttestationManifest(m));
  if (candidates.length === 0) return null;
  const exact = candidates.find(
    (m) => m.platform?.os === platform.os && m.platform?.architecture === platform.architecture,
  );
  return exact ?? candidates[0];
}

export function isImageIndex(body: OciIndex | OciManifest): body is OciIndex {
  return Array.isArray((body as OciIndex).manifests);
}

/** Host that serves the OCI distribution API for a registry reference. */
export function distributionApiHost(registry: string): string {
  const value = clean(registry).toLowerCase();
  if (value === DOCKER_HUB_REGISTRY || value === "index.docker.io") return DOCKER_HUB_API_HOST;
  return value;
}

/**
 * Parse `WWW-Authenticate: Bearer realm="...",service="...",scope="..."`.
 * Returns null for anything that is not a bearer challenge.
 */
export function parseBearerChallenge(header: string | undefined | null): BearerChallenge | null {
  const value = clean(header);
  if (!/^bearer\s/i.test(value)) return null;
  const params: Record<string, string> = {};
  const re = /([a-zA-Z_]+)="([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(value)) !== null) {
    params[match[1].toLowerCase()] = match[2];
  }
  if (!params.realm) return null;
  return { realm: params.realm, service: params.service, scope: params.scope };
}

/** Build the token URL for a bearer challenge (realm plus its query). */
export function tokenUrlFor(challenge: BearerChallenge, fallbackScope: string): string {
  const url = new URL(challenge.realm);
  if (challenge.service) url.searchParams.set("service", challenge.service);
  url.searchParams.set("scope", challenge.scope || fallbackScope);
  return url.toString();
}

/** `repository:<repo>:pull` — the only scope the check ever asks for. */
export function pullScopeFor(repository: string): string {
  return `repository:${repository}:pull`;
}

/** Links into the appliance repository, when the deployment knows its own. */
export function applianceLinks(
  repo: string | undefined | null,
  serverUrl: string,
): { repo: string; imageUpdateWorkflow: string; deployWorkflow: string; updateIssues: string } | null {
  const value = clean(repo);
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value)) return null;
  const base = `${serverUrl.replace(/\/+$/, "")}/${value}`;
  return {
    repo: value,
    imageUpdateWorkflow: `${base}/actions/workflows/${APPLIANCE_IMAGE_UPDATE_WORKFLOW}`,
    deployWorkflow: `${base}/actions/workflows/${APPLIANCE_DEPLOY_WORKFLOW}`,
    updateIssues: `${base}/issues?q=${encodeURIComponent(`is:open label:${APPLIANCE_UPDATE_ISSUE_LABEL}`)}`,
  };
}

/**
 * Parse the check interval: a non-negative integer number of minutes, `0`
 * disabling the check. Anything unparseable falls back to the default so a
 * typo never silently switches the check off.
 */
export function parseIntervalMinutes(raw: string | undefined | null, fallback: number): number {
  const value = clean(raw);
  if (!/^\d{1,6}$/.test(value)) return fallback;
  return Number.parseInt(value, 10);
}
