import { describe, expect, it } from "vitest";

import {
  applianceLinks,
  compareBuilds,
  componentOfTag,
  distributionApiHost,
  floatingTagFor,
  isImageIndex,
  parseBearerChallenge,
  parseImageReference,
  parseIntervalMinutes,
  pullScopeFor,
  selectPlatformManifest,
  shaOfTag,
  shaTagFor,
  shortSha,
  tokenUrlFor,
} from "./image-update-rules";

// A syntactically valid 40-hex commit SHA, assembled so it is obviously not a
// real credential (secret scanning flags literal high-entropy hex).
const FULL_SHA = "abc1234" + "0".repeat(33);

describe("parseImageReference", () => {
  it("parses the contract's web image reference", () => {
    expect(parseImageReference("docker.io/acme/cna:web-sha-abc1234")).toEqual({
      registry: "docker.io",
      repository: "acme/cna",
      tag: "web-sha-abc1234",
      digest: "",
    });
  });

  it("parses the appliances' pinned tag@digest form and keeps the component tag", () => {
    const digest = "sha256:" + "ab".repeat(32);
    expect(parseImageReference(`docker.io/acme/cna:web-sha-abc1234@${digest}`)).toEqual({
      registry: "docker.io",
      repository: "acme/cna",
      tag: "web-sha-abc1234",
      digest,
    });
    expect(parseImageReference(`docker.io/acme/cna@${digest}`)?.tag).toBe("");
    expect(parseImageReference("docker.io/acme/cna:web-sha-abc1234@sha256:abc")).toBeNull();
  });

  it("defaults registry and tag the way docker does", () => {
    expect(parseImageReference("acme/cna")).toEqual({
      registry: "docker.io",
      repository: "acme/cna",
      tag: "latest",
      digest: "",
    });
    expect(parseImageReference("postgres:16")?.repository).toBe("library/postgres");
  });

  it("keeps other registries and ports", () => {
    expect(parseImageReference("ghcr.io/acme/cna:api-latest")?.registry).toBe("ghcr.io");
    expect(parseImageReference("localhost:5000/cna:web-latest")).toEqual({
      registry: "localhost:5000",
      repository: "cna",
      tag: "web-latest",
      digest: "",
    });
  });

  it("accepts digest references and rejects garbage", () => {
    const digest = `sha256:${"a".repeat(64)}`;
    expect(parseImageReference(`docker.io/acme/cna@${digest}`)).toEqual({
      registry: "docker.io",
      repository: "acme/cna",
      tag: "",
      digest,
    });
    expect(parseImageReference("")).toBeNull();
    expect(parseImageReference("   ")).toBeNull();
    expect(parseImageReference("acme/cna:bad tag")).toBeNull();
    expect(parseImageReference("acme/cna@sha256:short")).toBeNull();
  });
});

describe("tag scheme", () => {
  // [tag, component, floating tag, short sha]
  const VECTORS: Array<[string, string, string, string]> = [
    ["web-sha-abc1234", "web", "web-latest", "abc1234"],
    ["api-sha-0123abc", "api", "api-latest", "0123abc"],
    ["worker-latest", "worker", "worker-latest", ""],
    ["migrator-sha-deadbee", "migrator", "migrator-latest", "deadbee"],
    ["sha-abc1234", "", "latest", "abc1234"],
    ["latest", "", "latest", ""],
    ["1.2.3", "", "latest", ""],
  ];

  it.each(VECTORS)("%s → component %s, floating %s, sha %s", (tag, component, floating, sha) => {
    expect(componentOfTag(tag)).toBe(component);
    expect(floatingTagFor(tag)).toBe(floating);
    expect(shaOfTag(tag)).toBe(sha);
  });

  it("builds the immutable tag of a revision", () => {
    expect(shaTagFor("web", FULL_SHA)).toBe("web-sha-abc1234");
    expect(shaTagFor("", "ABC1234")).toBe("sha-abc1234");
    expect(shaTagFor("web", "not-a-sha")).toBe("");
  });

  it("normalises short SHAs", () => {
    expect(shortSha(" ABCDEF0123 ")).toBe("abcdef0");
    expect(shortSha("abc")).toBe("");
    expect(shortSha(null)).toBe("");
  });
});

describe("compareBuilds", () => {
  it("never reports up-to-date without both sides", () => {
    expect(compareBuilds(null, "abc1234")).toBe("unknown");
    expect(compareBuilds("abc1234", "")).toBe("unknown");
    expect(compareBuilds("", "")).toBe("unknown");
  });

  it("compares on the short SHA the tags carry", () => {
    expect(compareBuilds(FULL_SHA, "ABC1234")).toBe("up-to-date");
    expect(compareBuilds("abc1234", "abc1235")).toBe("update-available");
  });
});

describe("selectPlatformManifest", () => {
  const index = {
    manifests: [
      {
        digest: "sha256:image",
        platform: { os: "linux", architecture: "amd64" },
      },
      {
        digest: "sha256:attestation",
        platform: { os: "unknown", architecture: "unknown" },
        annotations: { "vnd.docker.reference.type": "attestation-manifest" },
      },
    ],
  };

  it("skips buildx attestation manifests", () => {
    expect(selectPlatformManifest(index)?.digest).toBe("sha256:image");
    expect(isImageIndex(index)).toBe(true);
    expect(isImageIndex({ config: { digest: "sha256:cfg" } })).toBe(false);
  });

  it("falls back to the first runnable manifest and to null", () => {
    const arm = { manifests: [{ digest: "sha256:arm", platform: { os: "linux", architecture: "arm64" } }] };
    expect(selectPlatformManifest(arm)?.digest).toBe("sha256:arm");
    expect(selectPlatformManifest({ manifests: [index.manifests[1]] })).toBeNull();
    expect(selectPlatformManifest({})).toBeNull();
  });
});

describe("registry auth", () => {
  it("maps Docker Hub to its distribution API host", () => {
    expect(distributionApiHost("docker.io")).toBe("registry-1.docker.io");
    expect(distributionApiHost("index.docker.io")).toBe("registry-1.docker.io");
    expect(distributionApiHost("ghcr.io")).toBe("ghcr.io");
  });

  it("parses a bearer challenge and builds the token url", () => {
    const challenge = parseBearerChallenge(
      'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:acme/cna:pull"',
    );
    expect(challenge).toEqual({
      realm: "https://auth.docker.io/token",
      service: "registry.docker.io",
      scope: "repository:acme/cna:pull",
    });
    expect(tokenUrlFor(challenge!, pullScopeFor("acme/cna"))).toBe(
      "https://auth.docker.io/token?service=registry.docker.io&scope=repository%3Aacme%2Fcna%3Apull",
    );
  });

  it("uses the pull scope when the challenge carries none", () => {
    const challenge = parseBearerChallenge('Bearer realm="https://ghcr.io/token"');
    expect(tokenUrlFor(challenge!, pullScopeFor("acme/cna"))).toBe(
      "https://ghcr.io/token?scope=repository%3Aacme%2Fcna%3Apull",
    );
    expect(parseBearerChallenge("Basic realm=x")).toBeNull();
    expect(parseBearerChallenge(null)).toBeNull();
  });
});

describe("appliance links and interval", () => {
  it("builds the workflow and issue links for a valid owner/repo", () => {
    const links = applianceLinks("acme/Work-Cloud_Network_Azure_Appliance", "https://github.com/");
    expect(links?.imageUpdateWorkflow).toBe(
      "https://github.com/acme/Work-Cloud_Network_Azure_Appliance/actions/workflows/230-image-update.yml",
    );
    expect(links?.deployWorkflow).toBe(
      "https://github.com/acme/Work-Cloud_Network_Azure_Appliance/actions/workflows/210-deploy.yml",
    );
    expect(links?.updateIssues).toContain("label%3Aupdate-available");
    expect(applianceLinks("not a repo", "https://github.com")).toBeNull();
    expect(applianceLinks("", "https://github.com")).toBeNull();
  });

  it("parses the interval and falls back on garbage, keeping 0 as off", () => {
    expect(parseIntervalMinutes("30", 60)).toBe(30);
    expect(parseIntervalMinutes("0", 60)).toBe(0);
    expect(parseIntervalMinutes("", 60)).toBe(60);
    expect(parseIntervalMinutes("soon", 60)).toBe(60);
    expect(parseIntervalMinutes("-5", 60)).toBe(60);
  });
});
