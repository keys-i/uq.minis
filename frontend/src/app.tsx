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
import { MiniShelf } from "./shared/cards.tsx";
import { Pal } from "./wildlife/mascot.tsx";
import { Wildlife, ThemePicker } from "./shared/display.tsx";
import { Language, LanguagePicker } from "./shared/language.tsx";
import { Menu } from "./shared/menu.tsx";
import { useNotice } from "./shared/notice.ts";
import { useStudy } from "./study/store.ts";
import { useSession } from "./shared/session.ts";
import { Button, Dialog } from "./shared/controls.tsx";
import { miniHref, miniName, requestedMini } from "./shared/route.ts";

const readyRoutes = new Set(["home"]);

function editor<P>(name: string, load: () => Promise<React.ComponentType<P>>) {
  return lazy(() =>
    load().then((component) => {
      readyRoutes.add(name);
      return { default: component };
    }),
  );
}

const Timey = editor("timey", () => import("./timey/index.tsx").then((module) => module.Timey));
const Eventy = editor("event", () => import("./event.tsx").then((module) => module.Eventy));
const Planner = editor("planny", () =>
  import("./study/planner.tsx").then((module) => module.Planner),
);
const Buzzy = editor("buzzy", () => import("./study/buzzy.tsx").then((module) => module.Buzzy));
const Clubs = editor("clubby", () => import("./study/clubs.tsx").then((module) => module.Clubs));
const Courses = editor("scrappy", () =>
  import("./study/course.tsx").then((module) => module.Courses),
);
const Account = lazy(() =>
  import("./shared/account.tsx").then((module) => ({ default: module.Account })),
);
const CalendarSettings = lazy(() =>
  import("./study/calendar.tsx").then((module) => ({ default: module.CalendarSettings })),
);
const Tooltips = lazy(() =>
  import("./shared/tooltip.tsx").then((module) => ({ default: module.Tooltips })),
);
const NotFound = lazy(() =>
  import("./shared/lost.tsx").then((module) => ({ default: module.NotFound })),
);
const Footer = lazy(() =>
  import("./shared/footer.tsx").then((module) => ({ default: module.Footer })),
);

function changeView(name: string, update: () => void) {
  const still =
    typeof matchMedia === "function" &&
    matchMedia("(prefers-reduced-motion: reduce), (prefers-reduced-data: reduce)").matches;
  const tool = miniName(name);
  if (!document.startViewTransition || still || !readyRoutes.has(tool)) {
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
      ) : !known ? null : (
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
      ) : !known ? (
        <NotFound back={() => choose("home")} />
      ) : !access && tool !== "timey" && tool !== "event" ? (
        sessionError ? (
          <div className="notice error" role="alert">
            <p>{sessionError}</p>
            <Button onClick={() => void useSession.getState().load()}>Try again</Button>
          </div>
        ) : (
          <p role="status">Opening your workspace…</p>
        )
      ) : !plan && studying ? (
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
      ) : null}
    </>
  );
  return (
    <Language>
      <Wildlife>
        <Suspense fallback={null}>
          <Tooltips />
        </Suspense>
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
                <Pal key={tool} name={tool} page>
                  {content}
                </Pal>
              )}
            </Suspense>
            <Suspense fallback={null}>
              <Footer />
            </Suspense>
          </main>
        </div>
        {modal && (
          <Dialog title={modal.title} close={closeModal}>
            <Suspense fallback={<p role="status">Opening settings…</p>}>{modal.body}</Suspense>
          </Dialog>
        )}
      </Wildlife>
    </Language>
  );
}
