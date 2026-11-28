// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { saveTargetAs, SaveAsError } from "@/lib/save-as-service";
import { SaveAsTarget } from "./SaveAsTarget";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/save-as-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/save-as-service")>()),
  saveTargetAs: vi.fn(),
}));

const saveMock = vi.mocked(saveTargetAs);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function openEditor() {
  render(<SaveAsTarget id="t1" name="Downtown lunch" />);
  fireEvent.click(screen.getByRole("button", { name: "Save a copy of this analysis" }));
  return screen.getByLabelText("Name for the copy") as HTMLInputElement;
}

function save() {
  fireEvent.click(screen.getByRole("button", { name: "Save copy" }));
}

// S3-003: the small Save As form in the workspace.
describe("SaveAsTarget", () => {
  it("shows only a button until it is clicked", () => {
    render(<SaveAsTarget id="t1" name="Downtown lunch" />);

    expect(screen.getByRole("button", { name: "Save a copy of this analysis" })).toBeTruthy();
    expect(screen.queryByLabelText("Name for the copy")).toBeNull();
  });

  it("starts with a suggested name for the copy", () => {
    expect(openEditor().value).toBe("Downtown lunch (copy)");
  });

  it("says that Q&A history is not copied", () => {
    openEditor();

    expect(screen.getByText(/Questions and answers are not copied/)).toBeTruthy();
  });

  it("saves the chosen name and opens the new analysis", async () => {
    saveMock.mockResolvedValue({ id: "copy-1", name: "Lunch copy" });
    const field = openEditor();
    fireEvent.change(field, { target: { value: "Lunch copy" } });

    save();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/targets/copy-1"));
    expect(saveMock).toHaveBeenCalledWith("t1", "Lunch copy");
  });

  it("does not save an empty name and shows why", () => {
    const field = openEditor();
    fireEvent.change(field, { target: { value: "   " } });

    save();

    expect(screen.getByText("Enter a name for this analysis.")).toBeTruthy();
    expect(saveMock).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("shows the problem and stays on this analysis when saving fails", async () => {
    saveMock.mockRejectedValue(new SaveAsError("Could not save the copy. Nothing was changed. Please try again."));
    openEditor();

    save();

    expect(await screen.findByText("Could not save the copy. Nothing was changed. Please try again.")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("lets the user try again after a failure", async () => {
    saveMock.mockRejectedValueOnce(new SaveAsError("Could not reach the server. Check your connection and try again."));
    saveMock.mockResolvedValueOnce({ id: "copy-2", name: "Downtown lunch (copy)" });
    openEditor();

    save();
    await screen.findByText(/Could not reach the server/);
    save();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/targets/copy-2"));
  });

  it("Cancel closes the form without saving", () => {
    openEditor();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Name for the copy")).toBeNull();
    expect(saveMock).not.toHaveBeenCalled();
  });

  it("starts from the suggested name again after Cancel", () => {
    const field = openEditor();
    fireEvent.change(field, { target: { value: "Half typed" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Save a copy of this analysis" }));

    expect((screen.getByLabelText("Name for the copy") as HTMLInputElement).value).toBe("Downtown lunch (copy)");
  });
});
