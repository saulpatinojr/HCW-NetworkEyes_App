// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DRAWIO_EMBED_SRC } from "@/lib/drawio-embed";
import { DrawioEmbed } from "./DrawioEmbed";

// R-019: the editor is a sandboxed iframe on this deployment, and the host page talks to it with postMessage("*")
// because a sandboxed frame has an opaque origin. What makes that safe is who is answered and what is listened to,
// so these tests render the real component in jsdom and pin exactly that.

const SAVED = '{"event":"save","xml":"<mxfile>edited</mxfile>"}';
const INIT = '{"event":"init"}';

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(onSave?: (xml: string) => void, initialXml = "<mxfile>start</mxfile>") {
  act(() => root.render(<DrawioEmbed initialXml={initialXml} onSave={onSave} />));
  const frame = container.querySelector("iframe") as HTMLIFrameElement;
  const frameWindow = frame.contentWindow as Window;
  const reply = vi.spyOn(frameWindow, "postMessage").mockImplementation(() => {});
  return { frame, frameWindow, reply };
}

function post(source: Window | null, data: string, origin = "null") {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { data, origin, source }));
  });
}

describe("the iframe", () => {
  it("loads the self-hosted editor from a relative URL", () => {
    const { frame } = render();
    expect(frame.getAttribute("src")).toBe(DRAWIO_EMBED_SRC);
    expect(frame.getAttribute("src")?.startsWith("/drawio/")).toBe(true);
  });

  it("is sandboxed, with scripts but never the application's origin", () => {
    const { frame } = render();
    const tokens = (frame.getAttribute("sandbox") ?? "").split(/\s+/).filter(Boolean);
    expect(tokens).toContain("allow-scripts");
    expect(tokens).not.toContain("allow-same-origin");
    expect(tokens).not.toContain("allow-top-navigation");
  });
});

describe("the handshake", () => {
  it("answers init from its own iframe with the diagram, to that window only", () => {
    const { frameWindow, reply } = render(undefined, "<mxfile>start</mxfile>");
    post(frameWindow, INIT);
    expect(reply).toHaveBeenCalledTimes(1);
    const [message, target] = reply.mock.calls[0] as [string, string];
    expect(target).toBe("*");
    expect(JSON.parse(message)).toEqual({ action: "load", xml: "<mxfile>start</mxfile>", autosave: 0 });
  });

  it("forwards save to onSave and acknowledges it", () => {
    const onSave = vi.fn();
    const { frameWindow, reply } = render(onSave);
    post(frameWindow, SAVED);
    expect(onSave).toHaveBeenCalledExactlyOnceWith("<mxfile>edited</mxfile>");
    expect(JSON.parse((reply.mock.calls[0] as [string, string])[0])).toEqual({
      action: "status",
      message: "Saved to engagement",
      modified: false,
    });
  });

  it("ignores a message from another window, whatever it says", () => {
    const onSave = vi.fn();
    const { reply } = render(onSave);
    const other = document.createElement("iframe");
    document.body.appendChild(other);
    const otherReply = vi.spyOn(other.contentWindow as Window, "postMessage").mockImplementation(() => {});
    for (const source of [other.contentWindow, window, null]) {
      post(source, INIT);
      post(source, SAVED);
    }
    other.remove();
    expect(reply).not.toHaveBeenCalled();
    expect(otherReply).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("ignores its own iframe when the origin is not the sandbox's opaque origin", () => {
    const onSave = vi.fn();
    const { frameWindow, reply } = render(onSave);
    for (const origin of ["https://example.com", "http://localhost:3000", "", "NULL"]) {
      post(frameWindow, INIT, origin);
      post(frameWindow, SAVED, origin);
    }
    expect(reply).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("ignores messages that are not the editor's protocol", () => {
    const onSave = vi.fn();
    const { frameWindow, reply } = render(onSave);
    for (const data of ["", "not json", "null", "7", '{"event":"other"}', '{"event":"save"}', '{"event":"save","xml":1}']) {
      post(frameWindow, data);
    }
    expect(reply).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("stops listening when it unmounts", () => {
    const onSave = vi.fn();
    const { frameWindow, reply } = render(onSave);
    act(() => root.unmount());
    post(frameWindow, INIT);
    post(frameWindow, SAVED);
    expect(reply).not.toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
    root = createRoot(container); // afterEach unmounts it again
  });
});
