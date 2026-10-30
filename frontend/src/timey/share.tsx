/** Codes identify a project; the owner controls who can open and edit it */
import { useEffect, useRef, useState } from "react";
import * as z from "zod/mini";
import { api, read, request } from "../shared/api.ts";
import { useDraft } from "./draft.ts";
import { Icon } from "../shared/icons.tsx";
import { Issue, Status, message } from "./feedback.tsx";
const accessSchema = z.object({
  status: z.string(),
  notification: z.optional(z.nullable(z.string())),
});
const savedSchema = z.object({
  code: z.string(),
  revision: z.number(),
  link: z.optional(z.string()),
});
const projectsSchema = z.object({
  user: z.string(),
  projects: z.array(
    z.object({
      code: z.string(),
      title: z.string(),
      owner: z.string(),
      revision: z.number(),
      updated: z.number(),
    }),
  ),
});
const projectSchema = z.object({
  code: z.string(),
  title: z.string(),
  values: z.record(z.string(), z.string()),
  revision: z.number(),
  owner: z.string(),
  user: z.string(),
  members: z.array(z.object({ user: z.string(), status: z.string() })),
});
export function Share({ close }: { close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null),
    pending = useRef(false);
  const [code, setCode] = useState(
      () =>
        new URLSearchParams(typeof location === "undefined" ? "" : location.search)
          .get("join")
          ?.slice(0, 200) || "",
    ),
    [rows, setRows] = useState<z.infer<typeof projectsSchema>["projects"]>([]),
    [project, setProject] = useState<z.infer<typeof projectSchema> | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState("");
  const { values, shared, recovery } = useDraft();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    if (!project?.code) return;
    const code = project.code,
      controller = new AbortController();
    const refresh = setInterval(() => {
      if (document.hidden || pending.current) return;
      void api(`/api/timey/projects/${code}`, projectSchema, undefined, controller.signal)
        .then((data) => {
          if (!controller.signal.aborted) setProject(data);
        })
        .catch((error) => {
          if (!controller.signal.aborted) setError(message(error, "refreshing shared edits"));
        });
    }, 5000);
    return () => {
      clearInterval(refresh);
      controller.abort();
    };
  }, [project?.code]);
  async function perform(task: () => Promise<void>, status: string) {
    if (pending.current) return;
    pending.current = true;
    setBusy(status);
    setError("");
    try {
      await task();
    } catch (error) {
      setError(message(error, "sharing this project"));
    } finally {
      pending.current = false;
      setBusy("");
    }
  }
  async function list() {
    const data = await api("/api/timey/projects", projectsSchema);
    setRows(data.projects);
  }
  async function inspect(code: string) {
    const data = await api(`/api/timey/projects/${code}`, projectSchema);
    setProject(data);
    return data;
  }
  function apply(data: z.infer<typeof projectSchema>) {
    useDraft.setState((draft) => ({
      recovery: draft.values,
      values: data.values,
      phase: "edit",
      shared: { code: data.code, revision: data.revision },
    }));
    setNotice("Shared edits opened - your previous draft can be restored here");
  }
  async function save() {
    const body = {
      title: values.label || values.design_name || "My countdown",
      values,
      revision: shared?.revision || 0,
    };
    const result = shared
      ? await read(
          await request(`/api/timey/projects/${shared.code}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
          savedSchema,
        )
      : await api("/api/timey/projects", savedSchema, body);
    useDraft.setState({ shared: { code: result.code, revision: result.revision } });
    setCode(result.code);
    await inspect(result.code);
    setNotice("Your shared draft is saved");
    await list();
  }
  const link = shared ? `https://share.keysi.dev/timey/${shared.code}` : "";
  return (
    <dialog
      ref={dialog}
      className="timer-save timer-controls"
      aria-labelledby="share-title"
      onCancel={close}
      onClose={close}
    >
      <div className="save-heading">
        <h2 id="share-title">Make it together</h2>
        <button
          type="button"
          className="quiet"
          aria-label="Close sharing"
          data-tip="Close"
          onClick={close}
        >
          <Icon name="close" />
        </button>
      </div>
      <>
        <p>Share a code, then choose who joins your project</p>
        <div className="save-actions">
          <button
            type="button"
            disabled={!!busy}
            onClick={() => void perform(save, "Saving your shared draft…")}
          >
            {shared ? "Save shared edits" : "Share this draft"}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!!busy}
            onClick={() => void perform(list, "Opening your projects…")}
          >
            My projects
          </button>
        </div>
        {shared && (
          <div className="share-code">
            <strong>{shared.code}</strong>
            <div className="save-actions">
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  void perform(async () => {
                    await navigator.clipboard.writeText(link);
                    setNotice("Link copied");
                  }, "Copying…")
                }
              >
                Copy link
              </button>
              {typeof navigator.share === "function" && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    void perform(
                      async () => navigator.share({ title: "Make a timer together", url: link }),
                      "Opening share options…",
                    )
                  }
                >
                  Share…
                </button>
              )}
            </div>
            <small>People need your approval before opening it</small>
          </div>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void perform(async () => {
              const clean = code.trim().split("/").pop() || "";
              if (!/^[\w-]{12}$/.test(clean))
                throw new Error("Enter the twelve-character code or paste its share link");
              const status = await api(`/api/timey/projects/${clean}/request`, accessSchema, {});
              setCode(clean);
              if (status.status === "accepted") {
                apply(await inspect(clean));
              } else
                setNotice(
                  status.status === "rejected"
                    ? "The owner declined this request"
                    : "Your request is with the owner; return here once they approve",
                );
            }, "Asking the owner…");
          }}
        >
          <label className="field">
            <span>Join with a code</span>
            <input
              value={code}
              maxLength={200}
              onChange={(event) => setCode(event.target.value)}
              placeholder="Paste a code or link…"
            />
          </label>
          <button type="submit" className="secondary" disabled={!!busy}>
            Ask to join
          </button>
        </form>
        {rows.length > 0 && (
          <div className="share-projects">
            {rows.map((row) => (
              <button
                type="button"
                key={row.code}
                className="quiet"
                onClick={() =>
                  void perform(async () => {
                    await inspect(row.code);
                  }, "Opening the shared draft…")
                }
              >
                {row.title}
              </button>
            ))}
          </div>
        )}
        {project && (
          <section className="share-members">
            <h3>{project.title}</h3>
            <button
              type="button"
              className="secondary"
              disabled={!!busy}
              onClick={() => apply(project)}
            >
              Open this shared version
            </button>
            {project.owner === project.user &&
              project.members
                .filter((member) => member.status !== "rejected")
                .map((member) => (
                  <div className="share-person" key={member.user}>
                    <span>{member.user}</span>
                    {(member.status === "accepted" ? [false] : [true, false]).map((accept) => (
                      <button
                        type="button"
                        className={accept ? "" : "quiet"}
                        key={String(accept)}
                        onClick={() =>
                          void perform(async () => {
                            await read(
                              await request(`/api/timey/projects/${project.code}/access`, {
                                method: "PUT",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ user: member.user, accept }),
                              }),
                              accessSchema,
                            );
                            await inspect(project.code);
                          }, "Updating access…")
                        }
                      >
                        {accept
                          ? "Accept"
                          : member.status === "accepted"
                            ? "Remove access"
                            : "Decline"}
                      </button>
                    ))}
                  </div>
                ))}
          </section>
        )}
        {recovery && (
          <button
            type="button"
            className="quiet"
            onClick={() => {
              useDraft.setState((draft) => ({
                values: recovery,
                recovery: draft.values,
                phase: "edit",
                shared: null,
              }));
              setNotice("Your previous draft is back");
            }}
          >
            Restore my previous draft
          </button>
        )}
        {busy && <Status text={busy} />}
        <p role="status">{notice}</p>
        {error && (
          <Issue title="Your local draft is still here" message={error}>
            <button
              type="button"
              className="quiet"
              onClick={() =>
                void perform(async () => {
                  if (shared) await inspect(shared.code);
                }, "Checking shared edits…")
              }
            >
              Review the shared version
            </button>
          </Issue>
        )}
      </>
    </dialog>
  );
}
