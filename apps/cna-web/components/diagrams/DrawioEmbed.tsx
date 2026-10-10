"use client";

import { useEffect, useRef } from "react";

const DRAWIO_ORIGIN = "https://embed.diagrams.net";

/**
 * Embedded draw.io editor with the proto=json handshake completed.
 *
 * With proto=json, embed.diagrams.net shows its spinner and waits for the
 * host page to answer its "init" postMessage with a "load" action carrying
 * diagram XML. Without that reply the editor spins forever — which is
 * exactly what the previous bare <iframe> did.
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
      if (event.origin !== DRAWIO_ORIGIN) return;
      if (event.source !== frameRef.current?.contentWindow) return;

      let msg: { event?: string; xml?: string } | null = null;
      try {
        msg = JSON.parse(event.data as string) as { event?: string; xml?: string };
      } catch {
        return;
      }
      if (msg?.event === "init") {
        frameRef.current?.contentWindow?.postMessage(
          JSON.stringify({ action: "load", xml: initialXml, autosave: 0 }),
          DRAWIO_ORIGIN,
        );
      } else if (msg?.event === "save" && typeof msg.xml === "string") {
        onSaveRef.current?.(msg.xml);
        frameRef.current?.contentWindow?.postMessage(
          JSON.stringify({ action: "status", message: "Saved to engagement", modified: false }),
          DRAWIO_ORIGIN,
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
      src={`${DRAWIO_ORIGIN}/?embed=1&ui=min&spin=1&proto=json&libraries=1&noExitBtn=1`}
      className="h-[560px] w-full"
    />
  );
}
