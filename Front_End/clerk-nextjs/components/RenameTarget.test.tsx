// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renameTarget, RenameError } from "@/lib/rename-service";
import { RenameTarget } from "./RenameTarget";

vi.mock("@/lib/rename-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/rename-service")>()),
  renameTarget: vi.fn(),
}));

const renameMock = vi.mocked(renameTarget);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function setup() {
  const onRenamed = vi.fn();
  render(<RenameTarget id="t1" name="Downtown lunch" onRenamed={onRenamed} />);
  return { onRenamed };
}

function openEditor() {
  fireEvent.click(screen.getByRole("button", { name: "Rename this analysis" }));
  return screen.getByLabelText("New name") as HTMLInputElement;
}

function save() {
  fireEvent.click(screen.getByRole("button", { name: "Save name" }));
}

// S3-002: the small rename form in the workspace.
describe("RenameTarget", () => {
  it("shows the name and a Rename button, with no form until Rename is clicked", () => {
    setup();

    expect(screen.getByText("Downtown lunch")).toBeTruthy();
    expect(screen.queryByLabelText("New name")).toBeNull();
  });

  it("opens a form filled with the current name", () => {
    setup();

    expect(openEditor().value).toBe("Downtown lunch");
  });

  it("saves the new name, tells the page, and goes back to showing the name", async () => {
    renameMock.mockResolvedValue("Lunch spot downtown");
    const { onRenamed } = setup();

    fireEvent.change(openEditor(), { target: { value: "Lunch spot downtown" } });
    save();

    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith("Lunch spot downtown"));
    expect(renameMock).toHaveBeenCalledWith("t1", "Lunch spot downtown");
    expect(screen.queryByLabelText("New name")).toBeNull();
  });

  it("shows a message and sends nothing when the name is unusable", () => {
    const { onRenamed } = setup();

    fireEvent.change(openEditor(), { target: { value: "---" } });
    save();

    expect(screen.getByText("Use at least one letter or number in the name.")).toBeTruthy();
    expect(renameMock).not.toHaveBeenCalled();
    expect(onRenamed).not.toHaveBeenCalled();
  });

  it("shows a message when the name is left empty", () => {
    setup();

    fireEvent.change(openEditor(), { target: { value: "   " } });
    save();

    expect(screen.getByText("Enter a name for this analysis.")).toBeTruthy();
    expect(renameMock).not.toHaveBeenCalled();
  });

  it("just closes when the name did not change, without a request", () => {
    const { onRenamed } = setup();

    fireEvent.change(openEditor(), { target: { value: "  Downtown   lunch " } });
    save();

    expect(renameMock).not.toHaveBeenCalled();
    expect(onRenamed).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("New name")).toBeNull();
  });

  it("keeps the form open and the old name when the server says no", async () => {
    renameMock.mockRejectedValue(new RenameError("You don't have access to this target."));
    const { onRenamed } = setup();

    fireEvent.change(openEditor(), { target: { value: "Lunch spot downtown" } });
    save();

    expect(await screen.findByText("You don't have access to this target.")).toBeTruthy();
    expect(onRenamed).not.toHaveBeenCalled();
    expect((screen.getByLabelText("New name") as HTMLInputElement).value).toBe("Lunch spot downtown");
  });

  it("cancels without saving and shows the old name next time", () => {
    const { onRenamed } = setup();

    fireEvent.change(openEditor(), { target: { value: "Something else" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(renameMock).not.toHaveBeenCalled();
    expect(onRenamed).not.toHaveBeenCalled();
    expect(openEditor().value).toBe("Downtown lunch");
  });

  it("cannot be saved twice while the first save is still running", async () => {
    let finish!: (name: string) => void;
    renameMock.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    setup();

    fireEvent.change(openEditor(), { target: { value: "Lunch spot downtown" } });
    save();

    expect((screen.getByRole("button", { name: "Save name" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(true);
    finish("Lunch spot downtown");
    await waitFor(() => expect(screen.queryByLabelText("New name")).toBeNull());
    expect(renameMock).toHaveBeenCalledTimes(1);
  });
});
