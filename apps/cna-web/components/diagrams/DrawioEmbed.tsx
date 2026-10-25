"use client";

import { useEffect, useRef } from "react";
import {
  DRAWIO_EMBED_SRC,
  DRAWIO_IFRAME_SANDBOX,
  DRAWIO_MESSAGE_ORIGIN,
  parseDrawioMessage,
} from "@/lib/drawio-embed";

// The editor is the draw.io web app served by this deployment (lib/drawio-embed.ts), loaded into a sandboxed
// iframe with an opaque origin. Its messages therefore arrive with the origin "null", and a reply cannot name a
// target origin: "*" is the only value postMessage accepts for it. The reply is safe because it goes to
// `frameRef.current.contentWindow`, the one window this component created, and because the editor's CSP lets it
// send nothing to any other host.
const REPLY_TARGET = "*";

/**
 * Embedded draw.io editor with the proto=json handshake completed.
 *
 * With proto=json, the editor shows its spinner and waits for the host page
 * to answer its "init" postMessage with a "load" action carrying diagram
 * XML. Without that reply the editor spins forever — which is exactly what
 * the previous bare <iframe> did.
 *
 * The editor's Save button (and Ctrl+S) posts an "save" event carrying the
 * current XML; when `onSave` is provided we forward the XML to it and answer
 * with a "status" action so the editor clears its modified indicator.
 */
export function DrawioEmbed({
  initialXml = "",
  onSave,
}: {
  initialXml?: string;
  onSave?: (xml: string) => void;
}) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  // Keep the latest onSave without re-running the handshake effect. Written
  // in an effect, never during render (react-hooks/refs).
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.origin !== DRAWIO_MESSAGE_ORIGIN) return;

      const msg = parseDrawioMessage(event.data);
      if (msg?.event === "init") {
        frameRef.current?.contentWindow?.postMessage(
          JSON.stringify({ action: "load", xml: initialXml, autosave: 0 }),
          REPLY_TARGET,
        );
      } else if (msg?.event === "save" && typeof msg.xml === "string") {
        onSaveRef.current?.(msg.xml);
        frameRef.current?.contentWindow?.postMessage(
          JSON.stringify({ action: "status", message: "Saved to engagement", modified: false }),
          REPLY_TARGET,
        );
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [initialXml]);

  return (
    <iframe
      ref={frameRef}
      title="draw.io editor"
      src={DRAWIO_EMBED_SRC}
      sandbox={DRAWIO_IFRAME_SANDBOX}
      className="h-[560px] w-full"
    />
  );
}
