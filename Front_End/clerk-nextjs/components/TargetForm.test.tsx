// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TargetForm } from "./TargetForm";
import { createTarget, TargetValidationError } from "@/lib/targets-service";

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  loading: vi.fn(() => "toast-1"),
  dismiss: vi.fn(),
}));

vi.mock("./ui/Toast", () => ({ useToast: () => toast }));
vi.mock("@/lib/targets-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/targets-service")>()),
  createTarget: vi.fn(),
}));

const createTargetMock = vi.mocked(createTarget);

const GOOD_URL =
  "https://www.google.com/maps/place/Sample+Coffee/data=!4m7!3m6!1s0x89c25a2b1c1d3f3b:0x1a2b3c4d5e6f7a8b!8m2";

const saved = {
  id: "t1",
  name: "Sample Coffee",
  platform: "Google Maps",
  sourceUrl: GOOD_URL,
  createdAt: "2026-11-01T00:00:00Z",
  ingestionStatus: "not_started" as const,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function fillForm(name: string, url: string) {
  const nameInput = screen.getByPlaceholderText("e.g. Sample Coffee House") as HTMLInputElement;
  const urlInput = screen.getByPlaceholderText("https://www.google.com/maps/place/...") as HTMLInputElement;
  fireEvent.change(nameInput, { target: { value: name } });
  fireEvent.change(urlInput, { target: { value: url } });
  return { nameInput, urlInput };
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Create target" }));
}

describe("TargetForm", () => {
  it("shows messages under the fields and does not call the server when input is invalid", async () => {
    render(<TargetForm onCreated={vi.fn()} />);

    submit();

    expect(await screen.findByText("Enter the business or location name.")).toBeTruthy();
    expect(screen.getByText("Enter the link to the reviews.")).toBeTruthy();
    expect(createTargetMock).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Please fix the highlighted fields and try again.");
  });

  it("creates the target, clears the form and tells the parent", async () => {
    createTargetMock.mockResolvedValue(saved);
    const onCreated = vi.fn();
    render(<TargetForm onCreated={onCreated} />);
    const { nameInput, urlInput } = fillForm("Sample Coffee", GOOD_URL);

    submit();

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(saved));
    expect(createTargetMock).toHaveBeenCalledWith({ name: "Sample Coffee", sourceUrl: GOOD_URL });
    expect(nameInput.value).toBe("");
    expect(urlInput.value).toBe("");
    expect(toast.dismiss).toHaveBeenCalledWith("toast-1");
  });

  it("shows the server's message under the field when the server rejects the input", async () => {
    createTargetMock.mockRejectedValue(
      new TargetValidationError({ sourceUrl: "The server did not accept this link." })
    );
    const onCreated = vi.fn();
    render(<TargetForm onCreated={onCreated} />);
    fillForm("Sample Coffee", GOOD_URL);

    submit();

    expect(await screen.findByText("The server did not accept this link.")).toBeTruthy();
    expect(onCreated).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("The server rejected some fields. See the messages below.");
  });

  it("shows the error message when the request fails for another reason", async () => {
    createTargetMock.mockRejectedValue(new Error("Could not reach the server. Check your connection and try again."));
    const onCreated = vi.fn();
    render(<TargetForm onCreated={onCreated} />);
    fillForm("Sample Coffee", GOOD_URL);

    submit();

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not reach the server. Check your connection and try again.")
    );
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("falls back to a generic message when the failure is not an Error", async () => {
    createTargetMock.mockRejectedValue("weird failure");
    render(<TargetForm onCreated={vi.fn()} />);
    fillForm("Sample Coffee", GOOD_URL);

    submit();

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Could not create the target. Please try again.")
    );
  });
});
