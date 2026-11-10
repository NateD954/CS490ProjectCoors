// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { listTargets } from "@/lib/targets-service";
import HomePage from "./page";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

const newTarget = vi.hoisted(() => ({
  id: "new-1",
  name: "New Cafe",
  platform: "Google Maps",
  sourceUrl: "https://www.google.com/maps/place/x/data=!1s0x1:0x2",
  createdAt: "2026-11-01T00:00:00Z",
  ingestionStatus: "not_started",
}));

vi.mock("@/components/ui/Toast", () => ({
  ToastProvider: ({ children }: { children: ReactNode }) => children,
  useToast: () => toast,
}));
vi.mock("@/lib/targets-service", () => ({ listTargets: vi.fn() }));

// next/link needs the Next.js router, so replace it with a plain link.
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return {
    default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) =>
      createElement("a", { href, ...rest }, children),
  };
});

// The form and the list have their own tests. Here they are replaced with stand-ins
// that show what the page gave them and let the test trigger their callbacks.
vi.mock("@/components/TargetForm", async () => {
  const { createElement } = await import("react");
  return {
    TargetForm: ({ onCreated }: { onCreated: (target: unknown) => void }) =>
      createElement("button", { onClick: () => onCreated(newTarget) }, "create-stub"),
  };
});
vi.mock("@/components/TargetList", async () => {
  const { createElement } = await import("react");
  return {
    TargetList: ({
      targets,
      error,
      onRetry,
    }: {
      targets: { name: string }[] | null;
      error: string | null;
      onRetry: () => void;
    }) =>
      createElement(
        "div",
        null,
        createElement("p", null, error ?? "no error"),
        createElement("p", null, targets === null ? "loading" : `targets: ${targets.map((t) => t.name).join(",")}`),
        createElement("button", { onClick: onRetry }, "retry-stub")
      ),
  };
});

const listTargetsMock = vi.mocked(listTargets);
const existing = { ...newTarget, id: "t1", name: "Old Cafe" } as never;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Home page", () => {
  it("shows its two sections", async () => {
    listTargetsMock.mockResolvedValue([]);

    render(<HomePage />);

    expect(await screen.findByText("targets: ")).toBeTruthy();
    expect(screen.getByText("Create a new target")).toBeTruthy();
    expect(screen.getByText("Your targets")).toBeTruthy();
  });

  it("loads the user's targets and hands them to the list", async () => {
    listTargetsMock.mockResolvedValue([existing]);

    render(<HomePage />);

    expect(screen.getByText("loading")).toBeTruthy();
    expect(await screen.findByText("targets: Old Cafe")).toBeTruthy();
    expect(screen.getByText("no error")).toBeTruthy();
    expect(listTargetsMock).toHaveBeenCalledTimes(1);
  });

  it("shows an error when the targets cannot be loaded, and Try again loads them", async () => {
    listTargetsMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce([existing]);

    render(<HomePage />);
    expect(await screen.findByText("Could not load your targets. Please try again.")).toBeTruthy();

    fireEvent.click(screen.getByText("retry-stub"));

    expect(await screen.findByText("targets: Old Cafe")).toBeTruthy();
    expect(screen.getByText("no error")).toBeTruthy(); // the old error is cleared
    expect(listTargetsMock).toHaveBeenCalledTimes(2);
  });

  it("adds a newly created target to the top of the list and links to its workspace", async () => {
    listTargetsMock.mockResolvedValue([existing]);
    render(<HomePage />);
    await screen.findByText("targets: Old Cafe");

    fireEvent.click(screen.getByText("create-stub"));

    expect(screen.getByText("targets: New Cafe,Old Cafe")).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith('"New Cafe" was created.');
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText("New Cafe")).toBeTruthy(); // the name in the confirmation banner
    expect(screen.getByRole("link", { name: "Open workspace" }).getAttribute("href")).toBe("/targets/new-1");
  });

  it("still shows a newly created target when the first load has not finished", () => {
    listTargetsMock.mockReturnValue(new Promise(() => {})); // never finishes

    render(<HomePage />);
    fireEvent.click(screen.getByText("create-stub"));

    expect(screen.getByText("targets: New Cafe")).toBeTruthy();
  });

  it("does not show the confirmation banner before anything is created", async () => {
    listTargetsMock.mockResolvedValue([existing]);

    render(<HomePage />);
    await screen.findByText("targets: Old Cafe");

    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("link", { name: "Open workspace" })).toBeNull();
  });
});
