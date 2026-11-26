// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { AnalysisTarget } from "@/lib/types";
import { createComparison } from "@/lib/comparisons-service";
import { ComparisonForm } from "./ComparisonForm";

vi.mock("@/lib/comparisons-service", () => ({ createComparison: vi.fn() }));
const targets: AnalysisTarget[] = ["a", "b"].map((id) => ({ id, name: `Cafe ${id}`, platform: "Google Maps", sourceUrl: "https://google.com", createdAt: "2026-11-26T00:00:00Z", ingestionStatus: "not_started" }));
const saved = { id: "c1", name: "A vs B", target_a_id: "a", target_b_id: "b", created_at: "2026-11-26T00:00:00Z" };
const button = () => screen.getByRole("button", { name: "Save comparison" }) as HTMLButtonElement;

function fill(name = "A vs B", a = "a", b = "b") {
  fireEvent.change(screen.getByLabelText("Comparison name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Target A"), { target: { value: a } });
  fireEvent.change(screen.getByLabelText("Target B"), { target: { value: b } });
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("ComparisonForm", () => {
  it.each([{ rows: [] }, { rows: [targets[0]] }])("gives guidance when fewer than two targets exist: $rows.length", ({ rows }) => {
    render(<ComparisonForm targets={rows} onCreated={vi.fn()} />);
    expect(screen.getByText(/You need at least two analysis targets/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Create another target" }).getAttribute("href")).toBe("/home");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("requires a name and two distinct owned selections", () => {
    render(<ComparisonForm targets={targets} onCreated={vi.fn()} />);
    expect(button().disabled).toBe(true);
    fill("   ");
    expect(button().disabled).toBe(true);
    fill("A vs B", "a", "");
    expect(button().disabled).toBe(true);
    fill();
    expect(button().disabled).toBe(false);
    const a = screen.getByLabelText("Target A");
    const b = screen.getByLabelText("Target B");
    expect((within(b).getByRole("option", { name: "Cafe a" }) as HTMLOptionElement).disabled).toBe(true);
    expect((within(a).getByRole("option", { name: "Cafe b" }) as HTMLOptionElement).disabled).toBe(true);
    fireEvent.change(b, { target: { value: "a" } });
    expect(button().disabled).toBe(true);
    fireEvent.submit(button().closest("form")!);
    expect(createComparison).not.toHaveBeenCalled();
  });

  it("rejects a selection that disappeared from the owned target list", () => {
    const { rerender } = render(<ComparisonForm targets={targets} onCreated={vi.fn()} />);
    fill();
    rerender(<ComparisonForm targets={[targets[0], { ...targets[1], id: "c" }]} onCreated={vi.fn()} />);
    expect(button().disabled).toBe(true);
  });

  it("saves both targets, prevents repeat submissions, clears the form and reports success", async () => {
    let resolve!: (value: typeof saved) => void;
    vi.mocked(createComparison).mockReturnValue(new Promise((done) => { resolve = done; }));
    const onCreated = vi.fn();
    render(<ComparisonForm targets={targets} onCreated={onCreated} />);
    fill("  A vs B  ");
    fireEvent.click(button());
    expect(button().disabled).toBe(true);
    fireEvent.submit(button().closest("form")!);
    expect(createComparison).toHaveBeenCalledTimes(1);
    expect(createComparison).toHaveBeenCalledWith({ name: "A vs B", targetAId: "a", targetBId: "b" });
    resolve(saved);
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(saved));
    expect((screen.getByLabelText("Comparison name") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Target A") as HTMLSelectElement).value).toBe("");
  });

  it("shows API errors and lets the user retry without losing input", async () => {
    vi.mocked(createComparison).mockRejectedValueOnce(new Error("You don't have access to this target.")).mockResolvedValueOnce(saved);
    const onCreated = vi.fn();
    render(<ComparisonForm targets={targets} onCreated={onCreated} />);
    fill();
    fireEvent.click(button());
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "You don't have access to this target.");
    expect((screen.getByLabelText("Comparison name") as HTMLInputElement).value).toBe("A vs B");
    fireEvent.click(button());
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(saved));
  });
});
