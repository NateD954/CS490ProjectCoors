// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { listTargets } from "@/lib/targets-service";
import { TargetSwitcher } from "./TargetSwitcher";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/targets-service", () => ({ listTargets: vi.fn() }));

const listMock = vi.mocked(listTargets);

function t(id: string, name: string): AnalysisTarget {
  return { id, name, platform: "Google Maps", sourceUrl: "u", createdAt: "2026-10-31T12:00:00Z", ingestionStatus: "not_started" };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// S2-017 tests for TargetSwitcher: lists only your targets, switches, handles errors.
describe("TargetSwitcher (S2-017)", () => {
  it("lists only the targets the backend returns and marks the active one", async () => {
    listMock.mockResolvedValue([t("a", "Coffee A"), t("b", "Pizza B")]);

    render(<TargetSwitcher activeId="b" />);

    const select = (await screen.findByLabelText("Active target")) as HTMLSelectElement;
    expect(select.value).toBe("b");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Coffee A", "Pizza B"]);
  });

  it("opens the chosen target's workspace", async () => {
    listMock.mockResolvedValue([t("a", "Coffee A"), t("b", "Pizza B")]);

    render(<TargetSwitcher activeId="a" />);
    fireEvent.change(await screen.findByLabelText("Active target"), { target: { value: "b" } });

    expect(push).toHaveBeenCalledWith("/targets/b");
  });

  it("does not navigate when the active target is picked again", async () => {
    listMock.mockResolvedValue([t("a", "Coffee A"), t("b", "Pizza B")]);

    render(<TargetSwitcher activeId="a" />);
    fireEvent.change(await screen.findByLabelText("Active target"), { target: { value: "a" } });

    expect(push).not.toHaveBeenCalled();
  });

  it("shows a placeholder instead of a wrong name when the active id is not in the user's list", async () => {
    listMock.mockResolvedValue([t("a", "Coffee A")]);

    render(<TargetSwitcher activeId="someone-elses-id" />);

    const select = (await screen.findByLabelText("Active target")) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(screen.getByText("Select a target…")).toBeTruthy();
  });

  it("shows a short message when the list cannot be loaded", async () => {
    listMock.mockRejectedValue(new Error("boom"));

    render(<TargetSwitcher activeId="a" />);

    expect(await screen.findByText("Could not load your other targets.")).toBeTruthy();
  });
});
