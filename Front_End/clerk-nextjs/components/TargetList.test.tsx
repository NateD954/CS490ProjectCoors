// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import type { AnalysisTarget } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { TargetList } from "./TargetList";

// next/link needs the Next.js router, so replace it with a plain link.
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return {
    default: ({ href, children, ...rest }: { href: string; children?: ReactNode }) =>
      createElement("a", { href, ...rest }, children),
  };
});

const CREATED = "2026-10-31T12:00:00Z";

function target(overrides: Partial<AnalysisTarget> = {}): AnalysisTarget {
  return {
    id: "t1",
    name: "Sample Coffee",
    platform: "Google Maps",
    sourceUrl: "https://www.google.com/maps/place/Sample+Coffee/data=!1s0x1:0x2",
    createdAt: CREATED,
    ingestionStatus: "not_started",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("TargetList", () => {
  it("shows the error and lets the user retry", () => {
    const onRetry = vi.fn();
    render(<TargetList targets={null} error="Could not load your targets. Please try again." onRetry={onRetry} />);

    expect(screen.getByText("Could not load your targets. Please try again.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the error instead of the list when both are present", () => {
    render(<TargetList targets={[target()]} error="Something failed." onRetry={vi.fn()} />);

    expect(screen.getByText("Something failed.")).toBeTruthy();
    expect(screen.queryByText("Sample Coffee")).toBeNull();
  });

  it("shows a loading message while the targets are still loading", () => {
    render(<TargetList targets={null} error={null} onRetry={vi.fn()} />);

    expect(screen.getByText(/Loading your targets/)).toBeTruthy();
  });

  it("shows a helpful message when the user has no targets", () => {
    render(<TargetList targets={[]} error={null} onRetry={vi.fn()} />);

    expect(screen.getByText(/don't have any targets yet/)).toBeTruthy();
  });

  it("lists each target with a link to its workspace", () => {
    render(
      <TargetList
        targets={[target({ id: "a", name: "A's Cafe" }), target({ id: "b", name: "B's Bakery" })]}
        error={null}
        onRetry={vi.fn()}
      />
    );

    expect(screen.getByText("A's Cafe").closest("a")?.getAttribute("href")).toBe("/targets/a");
    expect(screen.getByText("B's Bakery").closest("a")?.getAttribute("href")).toBe("/targets/b");
    expect(screen.getAllByText("Google Maps")).toHaveLength(2);
    expect(screen.getAllByText("Not started")).toHaveLength(2);
    expect(screen.getAllByText(`Created ${formatDate(CREATED)}`)).toHaveLength(2);
  });
});
