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
import { flushSync } from "react-dom";
import { CalendarSettings } from "./study/calendar.tsx";
import { Tooltips } from "./shared/tooltip.tsx";
import { Trail, TrailWorld } from "./wildlife/trail.tsx";
import { Wildlife, ThemePicker } from "./shared/display.tsx";
import { Language, LanguagePicker } from "./shared/language.tsx";
import { Footer, Menu } from "./shared/menu.tsx";
import { useNotice } from "./shared/notice.ts";
import { useStudy } from "./study/store.ts";
import { useSession } from "./shared/session.ts";
import { Button, Dialog } from "./shared/controls.tsx";
import { Mini } from "./shared/mini.tsx";
import { Account } from "./shared/account.tsx";
import { miniHref, miniName, requestedMini } from "./shared/route.ts";

const readyRoutes = new Set(["home"]);
const lazyRoutes = new Set(["timey", "event", "planny", "buzzy", "clubby", "scrappy"]);

function editor<T>(name: string, load: () => Promise<T>) {
  return () =>
    load().then((module) => {
      readyRoutes.add(name);
      return module;
    });
}

const loadTimey = editor("timey", () => import("./timey/index.tsx"));
const loadEventy = editor("event", () => import("./event.tsx"));
const loadPlanner = editor("planny", () => import("./study/planner.tsx"));
const loadBuzzy = editor("buzzy", () => import("./study/buzzy.tsx"));
const loadClubs = editor("clubby", () => import("./study/clubs.tsx"));
const loadCourses = editor("scrappy", () => import("./study/course.tsx"));
const Timey = lazy(() => loadTimey().then((module) => ({ default: module.Timey })));
const Eventy = lazy(() => loadEventy().then((module) => ({ default: module.Eventy })));
const Planner = lazy(() => loadPlanner().then((module) => ({ default: module.Planner })));
const Buzzy = lazy(() => loadBuzzy().then((module) => ({ default: module.Buzzy })));
const Clubs = lazy(() => loadClubs().then((module) => ({ default: module.Clubs })));
const Courses = lazy(() => loadCourses().then((module) => ({ default: module.Courses })));
const PagePal = lazy(() =>
  import("./wildlife/mascot.tsx").then((module) => ({ default: module.Pal })),
);

function changeView(name: string, update: () => void) {
  const still =
    typeof matchMedia === "function" &&
    matchMedia("(prefers-reduced-motion: reduce), (prefers-reduced-data: reduce)").matches;
  const tool = miniName(name);
  if (!document.startViewTransition || still || (lazyRoutes.has(tool) && !readyRoutes.has(tool))) {
    startTransition(update);
    return;
  }
  document.startViewTransition(() => flushSync(update));
}

export default function App() {
  const initialRoute = useRef(requestedMini()).current;
  const [route, setRoute] = useState(initialRoute);
  const tool = miniName(route);
  const previousRoute = useRef(route);
  const [modal, setModal] = useState<{ title: string; body: React.ReactNode } | null>(null);
  const legacyAccount = useRef(initialRoute === "auth");
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
  const known = tool === "home" || Boolean(tools[tool]);
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
    if (previousRoute.current !== route) {
      document.querySelector<HTMLElement>("#main")?.focus({ preventScroll: true });
      previousRoute.current = route;
    }
  }, [route]);
  useEffect(() => {
    const back = () => {
      const name = requestedMini();
      changeView(name, () => setRoute(name));
    };
    addEventListener("popstate", back);
    return () => removeEventListener("popstate", back);
  }, []);
  function choose(name: string) {
    clear();
    history.pushState(null, "", miniHref(name));
    changeView(name, () => setRoute(name));
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
      {tool === "home" || !known ? null : (
        <header className="page-head">
          <h1 style={{ viewTransitionName: `mini-${tool}` }}>{title}</h1>
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
        <Trail tools={tools} open={choose} />
      ) : !known ? (
        <section className="not-found" aria-labelledby="not-found-title">
          <h1 id="not-found-title">That trail stop isn't here</h1>
          <p>The address may have changed, or this mini hasn't opened yet</p>
          <a
            className="button-link"
            href={miniHref("home")}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
              event.preventDefault();
              choose("home");
            }}
          >
            Back to the trail
          </a>
        </section>
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
        <Eventy follow={route === "agent"} />
      ) : tool === "timey" ? (
        <Timey />
      ) : tools[tool] ? (
        <Mini key={tool} name={tool} />
      ) : (
        <p role="status">Opening {title}…</p>
      )}
    </>
  );
  return (
    <Language>
      <Wildlife>
        <Tooltips />
        <TrailWorld route={route}>
          <a className="skip" href="#main">
            Skip to your tools
          </a>
          <div className={`shell ${tool === "home" ? "home" : ""}`}>
            <Menu tools={tools} tool={tool} choose={choose} account={account} />
            <main
              id="main"
              tabIndex={-1}
              data-mini={tool}
              className={tool === "home" || !known ? "" : "is-habitat"}
            >
              <Suspense fallback={<p role="status">Opening {title}…</p>}>
                {tool === "home" || !known ? (
                  content
                ) : (
                  <Suspense fallback={<div className="habitat-content">{content}</div>}>
                    <PagePal key={tool} name={tool} page>
                      {content}
                    </PagePal>
                  </Suspense>
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
        </TrailWorld>
      </Wildlife>
    </Language>
  );
}
