/** Save or publish without interrupting the editable project */
import { useEffect, useRef, useState } from "react";
import { api } from "../shared/api.ts";
import { resultSchema } from "../shared/schema.ts";
import { Icon } from "../shared/icons.tsx";
import { Issue, Status, message } from "./feedback.tsx";

export function Save({
  source,
  title,
  close,
}: {
  source: string;
  title: string;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    request = useRef<AbortController | null>(null);
  const [destination, setDestination] = useState(false),
    [name, setName] = useState(title || "My countdown"),
    [description, setDescription] = useState(""),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    return () => request.current?.abort();
  }, []);
  async function keep(upload: boolean) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(upload ? "Uploading your video…" : "Preparing your download…");
    setError("");
    try {
      const body = new FormData();
      body.set("source", source);
      body.set("title", name);
      body.set("description", description);
      body.set("destination", "youtube");
      body.set("confirm", "on");
      const result = await api(
        upload ? "/api/timey/publish" : "/api/timey/save",
        resultSchema,
        body,
        controller.signal,
      );
      if (upload) setNotice(result.result);
      else {
        const file = result.downloads?.[0];
        if (!file)
          throw new Error("Your download wasn't returned. Keep this window open and try again");
        const link = document.createElement("a");
        link.href = file.url;
        link.download = `${name.replace(/[^\p{L}\p{N} _.-]/gu, "-").trim() || "timer"}.mp4`;
        document.body.append(link);
        link.click();
        link.remove();
        setNotice("Your download is ready");
      }
    } catch (caught) {
      if (!controller.signal.aborted)
        setError(message(caught, upload ? "uploading the video" : "saving the video"));
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy("");
    }
  }
  return (
    <dialog
      ref={dialog}
      className="timer-save timer-controls"
      aria-labelledby="save-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else close();
      }}
      onClose={close}
    >
      <div className="save-heading">
        <h2 id="save-title">Save your video</h2>
        <button
          type="button"
          className="quiet"
          aria-label="Close save"
          data-tip="Close"
          disabled={!!busy}
          onClick={close}
        >
          <Icon name="close" />
        </button>
      </div>
      <>
        <label className="field">
          <span>Name</span>
          <input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} />
        </label>
        {!destination ? (
          <>
            <p>Would you like to upload a copy?</p>
            <div className="save-actions">
              <button type="button" disabled={!!busy} onClick={() => void keep(false)}>
                Save to this device
              </button>
              <button
                type="button"
                className="secondary"
                disabled={!!busy}
                onClick={() => setDestination(true)}
              >
                Upload a copy
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="field">
              <span>Description</span>
              <textarea
                value={description}
                maxLength={4000}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <p>Where would you like it?</p>
            <div className="save-actions">
              <button type="button" disabled={!!busy || !!notice} onClick={() => void keep(true)}>
                <Icon name="play" />
                YouTube
              </button>
              <button
                type="button"
                className="secondary"
                disabled
                data-tip="Keysi CDN isn't connected yet"
              >
                <Icon name="upload" />
                Keysi CDN
              </button>
            </div>
            <p className="save-note">Keysi CDN isn't connected yet</p>
            <button
              type="button"
              className="quiet"
              disabled={!!busy}
              onClick={() => setDestination(false)}
            >
              Back
            </button>
          </>
        )}
        {busy && <Status text={busy} />}
        {notice && <p role="status">{notice}</p>}
        {error && <Issue title="Your video is still here" message={error} />}
      </>
    </dialog>
  );
}
