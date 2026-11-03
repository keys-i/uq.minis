import { miniSchema } from "./schema.ts";
import type { MiniResult } from "../study/model.ts";
import React, { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api.ts";
const MiniForm = lazy(() => import("./forms.tsx").then((module) => ({ default: module.MiniForm })));
import { useNotice } from "./notice.ts";
import { Link } from "./controls.tsx";
import { useSession } from "./session.ts";

export function Mini({ name, action }: { name: string; action?: string }) {
  const file = (url: string) =>
    ["event", "auth", "agent"].includes(name) && url.startsWith("/download/")
      ? `${url}?uq=on`
      : url;
  const [schema, setSchema] = useState<MiniResult | null>(null),
    [busy, setBusy] = useState(false),
    report = useNotice((state) => state.report),
    workspace = useSession((state) => state.workspace);
  useEffect(() => {
    const controller = new AbortController();
    api(`/api/minis/${name}`, miniSchema, undefined, controller.signal)
      .then(setSchema)
      .catch((error) => {
        if (error.name !== "AbortError") report((error as Error).message, true);
      });
    return () => controller.abort();
  }, [name]);
  if (!schema) return <p role="status">Opening your mini…</p>;
  const formSchema = action
    ? {
        ...schema,
        submit: "Connect Outlook",
        fields: schema.fields.filter((field) =>
          ["mailbox", "username", "backend", "client_id", "tenant_id", "state_dir"].includes(
            field.name,
          ),
        ),
      }
    : schema;
  return (
    <>
      <p>{schema.about}</p>
      {schema.result && (
        <div className="notice" role="status">
          {schema.result}
        </div>
      )}
      {schema.downloads && (
        <div className="row">
          {schema.downloads.map((item) => (
            <a key={item.url} href={file(item.url)}>
              Download {item.name}
            </a>
          ))}
        </div>
      )}
      {schema.image && (
        <img className="preview" src={file(schema.image)} alt="Your rendered timer preview" />
      )}
      {!!schema.rows?.length && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {schema.columns?.map((key) => (
                  <th key={key} scope="col">
                    {key.replaceAll("_", " ")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {schema.rows?.map((row, i) => (
                <tr key={i}>
                  {schema.columns?.map((key) => (
                    <td key={key}>
                      {String(row[key] ?? "").startsWith("https://") ? (
                        <Link href={String(row[key])}>Open source</Link>
                      ) : (
                        String(row[key] ?? "")
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Suspense fallback={<p role="status">Opening your options…</p>}>
        <MiniForm
          key={`${name}:${workspace || "local"}:${JSON.stringify(formSchema.fields)}`}
          schema={formSchema}
          busy={busy}
          draft={action ? undefined : { workspace: workspace || "local", mini: name }}
          submit={async (body) => {
            if (action) body.set("action", action);
            if (
              [...body.values()].some(
                (value) => value instanceof File && value.size > 8 * 1024 * 1024,
              )
            ) {
              report("Choose files smaller than 8 MiB", true);
              return;
            }
            setBusy(true);
            try {
              setSchema(await api(`/api/minis/${name}`, miniSchema, body));
            } catch (error) {
              report((error as Error).message, true);
            } finally {
              setBusy(false);
            }
          }}
        />
      </Suspense>
      {schema.note && <p className="rule-note">{schema.note}</p>}
    </>
  );
}
