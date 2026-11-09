/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TProperty, TValue } from "../types";
import { choice, prop } from "./fixtures";

vi.mock("@/components/dropdowns/date", () => ({ DateDropdown: () => null }));
vi.mock("@/components/dropdowns/member/dropdown", () => ({ MemberDropdown: () => null }));
vi.mock("@/hooks/store/use-member", () => ({
  useMember: () => ({ getUserDetails: (id: string) => ({ display_name: id === "u1" ? "Ann" : undefined }) }),
}));

const { PropertyValueEditor } = await import("../values/value-editor");

afterEach(cleanup);

const renderEditor = (p: TProperty, value: TValue, disabled = false) => {
  const onChange = vi.fn();
  render(<PropertyValueEditor prop={p} value={value} disabled={disabled} projectId="p1" onChange={onChange} />);
  return onChange;
};

describe("InlineInput", () => {
  it("saves on Enter", async () => {
    const onChange = renderEditor(prop({ name: "Customer" }), null);
    await userEvent.click(screen.getByText("Add Customer"));
    await userEvent.type(screen.getByRole("textbox"), "Acme{Enter}");
    expect(onChange).toHaveBeenCalledWith("Acme");
  });

  it("cancels on Escape", async () => {
    const onChange = renderEditor(prop(), "Acme");
    await userEvent.click(screen.getByText("Acme"));
    await userEvent.type(screen.getByRole("textbox"), "zzz{Escape}");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("Acme")).toBeTruthy();
  });

  it("clears to null on blur", async () => {
    const onChange = renderEditor(prop(), "Acme");
    await userEvent.click(screen.getByText("Acme"));
    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.tab();
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("won't save a number it can't read, and sends numbers as numbers", async () => {
    const onChange = renderEditor(prop({ type: "number", name: "Points" }), null);
    await userEvent.click(screen.getByText("Add Points"));
    await userEvent.type(screen.getByRole("textbox"), "abc{Enter}");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox").getAttribute("aria-invalid")).toBe("true");
    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), "2.50{Enter}");
    expect(onChange).toHaveBeenCalledWith(2.5);
  });

  it("links a url", () => {
    renderEditor(prop({ type: "url" }), "https://plane.so/x");
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("https://plane.so/x");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });
});

describe("BooleanEditor", () => {
  it("toggles", async () => {
    const onChange = renderEditor(prop({ type: "boolean" }), null);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("ChoiceEditor", () => {
  it("keeps a held disabled option, tagged, and removes a chip", async () => {
    const tags = choice({
      multiple: true,
      options: [
        { id: "a", label: "Alpha", disabled: false },
        { id: "b", label: "Beta", disabled: true },
      ],
    });
    const onChange = renderEditor(tags, ["a", "b"]);
    expect(screen.getByText("disabled")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Remove Alpha/ }));
    expect(onChange).toHaveBeenCalledWith(["b"]);
  });

  it("clears a single choice", async () => {
    const onChange = renderEditor(choice({ name: "Repo" }), "a");
    await userEvent.click(screen.getByRole("button", { name: "Clear Repo" }));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});

describe("datetime time", () => {
  const due = prop({ name: "Due", type: "datetime" });
  const at = new Date(2026, 10, 9, 9, 0).toISOString();

  it("saves the time once, on blur", () => {
    const onChange = renderEditor(due, at);
    const input = screen.getByLabelText("Due time");
    fireEvent.change(input, { target: { value: "01:00" } });
    fireEvent.change(input, { target: { value: "14:30" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(new Date(2026, 10, 9, 14, 30).toISOString());
  });

  it("saves on Enter", () => {
    const onChange = renderEditor(due, at);
    const input = screen.getByLabelText("Due time");
    fireEvent.change(input, { target: { value: "10:15" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(new Date(2026, 10, 9, 10, 15).toISOString());
  });

  it("ignores a half-cleared time", () => {
    const onChange = renderEditor(due, at);
    const input = screen.getByLabelText("Due time");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.blur(input);
    expect(onChange).not.toHaveBeenCalled();
    expect((input as HTMLInputElement).value).toBe("09:00");
  });
});

describe("read-only", () => {
  it("shows text without an editor", async () => {
    const onChange = renderEditor(prop(), "Acme", true);
    await userEvent.click(screen.getByText("Acme"));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows member names and choice labels", () => {
    renderEditor(prop({ type: "member" }), "u1", true);
    expect(screen.getByText("Ann")).toBeTruthy();
    cleanup();
    renderEditor(choice({ multiple: true }), ["a"], true);
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
