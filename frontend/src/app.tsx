/** Compose mini pages around shared navigation; saved plans and identity live in their stores */
import React, {
  lazy,
  startTransition,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { CalendarSettings } from "./study/calendar.tsx";
import { Tooltips } from "./shared/tooltip.tsx";
import { MiniShelf } from "./shared/cards.tsx";
import { Pal } from "./wildlife/mascot.tsx";
import { Wildlife, ThemePicker } from "./shared/display.tsx";
import { Language, LanguagePicker } from "./shared/language.tsx";
import { Footer, Menu } from "./shared/menu.tsx";
import { useNotice } from "./shared/notice.ts";
import { useStudy } from "./study/store.ts";
import { useSession } from "./shared/session.ts";
import { Button, Dialog } from "./shared/controls.tsx";
import { Mini } from "./shared/mini.tsx";
import { Account } from "./shared/account.tsx";

const Timey = lazy(() => import("./timey/index.tsx").then((module) => ({ default: module.Timey })));
const Eventy = lazy(() => import("./event.tsx").then((module) => ({ default: module.Eventy })));
const Planner = lazy(() =>
  import("./study/planner.tsx").then((module) => ({ default: module.Planner })),
);
const Buzzy = lazy(() => import("./study/buzzy.tsx").then((module) => ({ default: module.Buzzy })));
const Clubs = lazy(() => import("./study/clubs.tsx").then((module) => ({ default: module.Clubs })));
const Courses = lazy(() =>
  import("./study/course.tsx").then((module) => ({ default: module.Courses })),
);

const route = (name: string) => (name === "agent" ? "event" : name === "auth" ? "home" : name);
const requested = () => {
  const query = new URLSearchParams(location.search);
  return query.get("m") || query.get("mini") || "home";
};

export default function App() {
  const [tool, setTool] = useState(route(requested()));
  const [modal, setModal] = useState<{ title: string; body: React.ReactNode } | null>(null);
  const legacyAccount = useRef(requested() === "auth");
  const tools = useStudy((state) => state.tools),
    plan = useStudy((state) => state.plan),
    saving = useStudy((state) => state.saving);
  const change = useStudy((state) => state.change);
  const message = useNotice((state) => state.message),
    report = useNotice((state) => state.report),
    clear = useNotice((state) => state.clear);
  const closeModal = useCallback(() => setModal(null), []);
  const hosted = useSession((state) => state.hosted),
    workspace = useSession((state) => state.workspace),
    sessionError = useSession((state) => state.error);
  const [planError, setPlanError] = useState("");
  const studying = ["planny", "buzzy", "scrappy", "clubby"].includes(tool);
  const access = hosted === false || !!workspace;
  useEffect(() => {
    // Warm the editors after home paints without starting backend workspaces
    const timer = setTimeout(() => {
      void Promise.allSettled([
        import("./timey/index.tsx"),
        import("./event.tsx"),
        import("./study/planner.tsx"),
        import("./study/buzzy.tsx"),
        import("./study/clubs.tsx"),
        import("./study/course.tsx"),
      ]);
    }, 0);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    useStudy
      .getState()
      .catalogue(controller.signal)
      .catch((error) => {
        if (error.name !== "AbortError") report(error.message, true);
      });
    return () => controller.abort();
  }, [report]);
  useEffect(() => {
    if (!access || !studying) return;
    const controller = new AbortController();
    setPlanError("");
    useStudy
      .getState()
      .load(controller.signal)
      .catch((error) => {
        if (error.name !== "AbortError") {
          setPlanError(error.message);
          if (useStudy.getState().plan) report("Your saved plan is here. " + error.message, true);
        }
      });
    return () => controller.abort();
  }, [access, report, studying]);
  useEffect(() => {
    const back = () => startTransition(() => setTool(route(requested())));
    addEventListener("popstate", back);
    return () => removeEventListener("popstate", back);
  }, []);
  function choose(name: string) {
    name = route(name);
    startTransition(() => setTool(name));
    clear();
    history.pushState(
      null,
      "",
      name === "home" ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}?m=${name}`,
    );
  }
  const title = tools[tool]?.title || tool;
  const calendar = () =>
    setModal({
      title: "Your calendar & backup",
      body: <CalendarSettings base={`${location.origin}${location.pathname}`} />,
    });
  const account = () => setModal({ title: "Account & settings", body: <Account /> });
  useEffect(() => {
    if (legacyAccount.current) {
      legacyAccount.current = false;
      account();
    }
  }, []);
  const content = (
    <>
      <div className="page-tools">
        <LanguagePicker />
        <ThemePicker />
      </div>
      {tool === "home" ? (
        <>
          <header className="welcome">
            <div>
              <h1>
                Big plans,
                <br />
                wild little helpers
              </h1>
              <p>Plan the semester, find your people and leave room for the good stuff</p>
            </div>
            <Pal name="hello" controls={false} />
          </header>
          <div className="wildlife-toolbar">
            <span>Pick your next little adventure</span>
          </div>
        </>
      ) : (
        <header className="page-head">
          <h1>{title}</h1>
          {plan && (
            <span className="save-state" role="status">
              {saving ? "Saving…" : "All saved"}
            </span>
          )}
        </header>
      )}
      {message && (
        <div
          className={`notice ${message.error ? "error" : ""}`}
          role={message.error ? "alert" : "status"}
        >
          {message.text}
        </div>
      )}
      {tool === "home" ? (
        <MiniShelf tools={tools} open={choose} />
      ) : !access && tool !== "timey" && tool !== "event" ? (
        sessionError ? (
          <div className="notice error" role="alert">
            <p>{sessionError}</p>
            <Button onClick={() => void useSession.getState().load()}>Try again</Button>
          </div>
        ) : (
          <p role="status">Opening your workspace…</p>
        )
      ) : !plan && ["planny", "buzzy", "scrappy", "clubby"].includes(tool) ? (
        planError ? (
          <div className="notice error" role="alert">
            <p>{planError}</p>
            <Button
              onClick={() => {
                setPlanError("");
                void useStudy
                  .getState()
                  .load()
                  .catch((error) => setPlanError(error.message));
              }}
            >
              Try again
            </Button>
          </div>
        ) : (
          <p role="status">Opening your saved plan…</p>
        )
      ) : tool === "planny" ? (
        plan && (
          <Planner plan={plan} change={change} modal={setModal} courses={() => choose("scrappy")} />
        )
      ) : tool === "buzzy" ? (
        plan && (
          <Buzzy plan={plan} change={change} modal={setModal} calendar={calendar} choose={choose} />
        )
      ) : tool === "scrappy" ? (
        plan && (
          <Courses
            plan={plan}
            change={change}
            modal={setModal}
            continuePlan={() => choose("planny")}
          />
        )
      ) : tool === "clubby" ? (
        plan && <Clubs plan={plan} change={change} modal={setModal} />
      ) : tool === "event" ? (
        <Eventy follow={requested() === "agent"} />
      ) : tool === "timey" ? (
        <Timey />
      ) : tools[tool] ? (
        <Mini key={tool} name={tool} />
      ) : (
        <p>Choose a mini from the menu</p>
      )}
    </>
  );
  return (
    <Language>
      <Wildlife>
        <Tooltips />
        <a className="skip" href="#main">
          Skip to your tools
        </a>
        <div className={`shell ${tool === "home" ? "home" : ""}`}>
          <Menu tools={tools} tool={tool} choose={choose} account={account} />
          <main
            id="main"
            tabIndex={-1}
            data-mini={tool}
            className={tool === "home" ? "" : "is-habitat"}
          >
            <Suspense fallback={<p role="status">Opening {title}…</p>}>
              {tool === "home" ? (
                content
              ) : (
                <Pal key={tool} name={tool} page thoughts>
                  {content}
                </Pal>
              )}
            </Suspense>
            <Footer />
          </main>
        </div>
        {modal && (
          <Dialog title={modal.title} close={closeModal}>
            {modal.body}
          </Dialog>
        )}
      </Wildlife>
    </Language>
  );
}
