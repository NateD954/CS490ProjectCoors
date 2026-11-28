// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TargetForm } from "./TargetForm";

vi.mock("./ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), loading: vi.fn(() => "x"), dismiss: vi.fn() }),
}));
vi.mock("@/lib/targets-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/targets-service")>()),
  createTarget: vi.fn(),
}));

const URL_A =
  "https://www.google.com/maps/place/Chipotle+Mexican+Grill/data=!4m7!3m6!1s0x89c2fa2bfb0d27d5:0xcceef158b20fbf10!8m2";
const URL_B = "https://www.google.com/maps/place/Sample+Coffee/data=!4m7!3m6!1s0x89c25a2b1c1d3f3b:0x1a2b3c4d5e6f7a8b!8m2";

afterEach(cleanup);

function fields() {
  render(<TargetForm onCreated={vi.fn()} />);
  return {
    name: screen.getByPlaceholderText("e.g. Sample Coffee House") as HTMLInputElement,
    url: screen.getByPlaceholderText("https://www.google.com/maps/place/...") as HTMLInputElement,
  };
}

// S3-001: the name is suggested from the link but never forced on the user.
describe("TargetForm name suggestion", () => {
  it("fills in a suggested name when a link is pasted and says it is only a suggestion", () => {
    const { name, url } = fields();

    fireEvent.change(url, { target: { value: URL_A } });

    expect(name.value).toBe("Chipotle Mexican Grill");
    expect(screen.getByText("Suggested from the link. Change it to any name you like.")).toBeTruthy();
  });

  it("follows the link while the user has not typed their own name", () => {
    const { name, url } = fields();

    fireEvent.change(url, { target: { value: URL_A } });
    fireEvent.change(url, { target: { value: URL_B } });

    expect(name.value).toBe("Sample Coffee");
  });

  it("never overwrites a name the user typed", () => {
    const { name, url } = fields();

    fireEvent.change(name, { target: { value: "Downtown lunch spot" } });
    fireEvent.change(url, { target: { value: URL_A } });

    expect(name.value).toBe("Downtown lunch spot");
    expect(screen.queryByText(/Suggested from the link/)).toBeNull();
  });

  it("keeps the user's edit of a suggested name when the link changes later", () => {
    const { name, url } = fields();

    fireEvent.change(url, { target: { value: URL_A } });
    fireEvent.change(name, { target: { value: "My favourite burrito place" } });
    fireEvent.change(url, { target: { value: URL_B } });

    expect(name.value).toBe("My favourite burrito place");
  });

  it("suggests again after the user clears the name box", () => {
    const { name, url } = fields();

    fireEvent.change(name, { target: { value: "Mine" } });
    fireEvent.change(name, { target: { value: "" } });
    fireEvent.change(url, { target: { value: URL_A } });

    expect(name.value).toBe("Chipotle Mexican Grill");
  });
});
