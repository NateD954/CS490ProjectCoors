// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { isValidElement, Suspense, type ReactElement, type ReactNode } from "react";
import TargetPage from "./page";

vi.mock("@/components/ui/Toast", () => ({
  ToastProvider: ({ children }: { children: ReactNode }) => children,
}));

// The workspace and the question box have their own tests. These stand-ins show
// which target id each one was given.
vi.mock("@/components/TargetWorkspace", async () => {
  const { createElement } = await import("react");
  return {
    TargetWorkspace: ({ id }: { id: string }) => createElement("div", null, `workspace for ${id}`),
  };
});
vi.mock("@/components/ReviewQA", async () => {
  const { createElement, useState } = await import("react");
  return {
    default: function MockReviewQA({ targetId }: { targetId: string }) {
      const [mountedTargetId] = useState(targetId);
      return createElement("div", null, `qa for ${mountedTargetId}`);
    },
  };
});

// The switcher needs the Next.js router and has its own tests (TargetSwitcher.test.tsx).
vi.mock("@/components/TargetSwitcher", async () => {
  const { createElement } = await import("react");
  return { TargetSwitcher: () => createElement("div", null, "switcher") };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---- helpers for looking inside the page -------------------------------------
// The page waits for the address's id inside an async server component, which a
// browser-style renderer cannot render directly. So the tests find that component in
// the page, run it themselves, and render what it returns.

type Props = { children?: ReactNode };

function walk(node: ReactNode, visit: (element: ReactElement<Props>) => void) {
  if (Array.isArray(node)) {
    node.forEach((child) => walk(child, visit));
    return;
  }
  if (isValidElement<Props>(node)) {
    visit(node);
    walk(node.props.children, visit);
  }
}

function collect(node: ReactNode, test: (element: ReactElement<Props>) => boolean) {
  const found: ReactElement<Props>[] = [];
  walk(node, (element) => {
    if (test(element)) found.push(element);
  });
  return found;
}

function pageFor(id: string) {
  return TargetPage({ params: Promise.resolve({ id }) });
}

function suspenseIn(page: ReactNode) {
  const [suspense] = collect(page, (element) => element.type === Suspense);
  expect(suspense).toBeDefined();
  return suspense as ReactElement<{ fallback: ReactNode; children: ReactNode }>;
}

async function loadWorkspace(id: string) {
  const suspense = suspenseIn(pageFor(id));
  const [loader] = collect(
    suspense.props.children,
    (element) => typeof element.type === "function" && element.type.constructor.name === "AsyncFunction"
  );
  expect(loader).toBeDefined();
  return await (loader.type as (props: unknown) => Promise<ReactNode>)(loader.props);
}

async function renderLoaded(id: string) {
  return render(<>{await loadWorkspace(id)}</>);
}

// ---- tests -------------------------------------------------------------------

describe("Target page", () => {
  it("shows a loading message while the address is being read", () => {
    const { fallback } = suspenseIn(pageFor("t1")).props;

    render(<>{fallback}</>);

    expect(screen.getByText(/Loading workspace/)).toBeTruthy();
  });

  it("gives the workspace the id from the address", async () => {
    await renderLoaded("t1");

    expect(screen.getByText("workspace for t1")).toBeTruthy();
  });

  it("uses whatever id is in the address, not a fixed one", async () => {
    await renderLoaded("another-id");

    expect(screen.getByText("workspace for another-id")).toBeTruthy();
    expect(screen.queryByText("workspace for t1")).toBeNull();
  });

  it("gives every part of the page that needs a target the same id", async () => {
    await renderLoaded("t9");

    expect(screen.getByText("qa for t9")).toBeTruthy();
    expect(screen.getByText("workspace for t9")).toBeTruthy();
  });

  it("resets the workspace and question box when the active target changes", async () => {
    const { rerender } = await renderLoaded("t1");
    expect(screen.getByText("qa for t1")).toBeTruthy();

    rerender(<>{await loadWorkspace("t2")}</>);

    expect(screen.getByText("workspace for t2")).toBeTruthy();
    expect(screen.getByText("qa for t2")).toBeTruthy();
    expect(screen.queryByText("qa for t1")).toBeNull();
  });

  it("is wrapped so that notifications work anywhere on the page", () => {
    const page = pageFor("t1");

    const main = collect(page, (element) => element.type === "main");

    expect(main).toHaveLength(1);
  });
});
