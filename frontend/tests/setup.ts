import { afterEach, beforeEach, vi } from "vitest";
import { useDraft } from "../src/timey/draft.ts";
import { useSession } from "../src/shared/session.ts";
import { queries } from "../src/shared/query.ts";
import { bind } from "../src/shared/api.ts";

afterEach(() => vi.useRealTimers());
beforeEach(() => {
  queries.clear();
  if (typeof sessionStorage !== "undefined") sessionStorage.clear();
  bind();
  useSession.setState({ hosted: false, user: "", workspace: null, error: "" });
  useDraft.setState({
    values: {},
    phase: "edit",
    movie: null,
    questions: [],
    shared: null,
    recovery: null,
  });
});
