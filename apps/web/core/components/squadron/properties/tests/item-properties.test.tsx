/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TPropertiesApi } from "../service";
import { PropertiesStore } from "../store";
import type { TProperty } from "../types";
import { prop } from "./fixtures";

const toast = vi.hoisted(() => vi.fn());
const holder = vi.hoisted(() => ({ store: undefined as unknown }));

vi.mock("@plane/propel/toast", () => ({ TOAST_TYPE: { ERROR: "error" }, setToast: toast }));
vi.mock("@/components/dropdowns/date", () => ({ DateDropdown: () => null }));
vi.mock("@/components/dropdowns/member/dropdown", () => ({ MemberDropdown: () => null }));
vi.mock("@/hooks/store/use-member", () => ({ useMember: () => ({ getUserDetails: () => undefined }) }));
vi.mock("../use-properties", () => ({ useProperties: () => holder.store }));

const { ItemCustomProperties } = await import("../item-properties");

afterEach(() => {
  cleanup();
  toast.mockReset();
});

const setup = (
  defs: TProperty[],
  values: Record<string, string | null>,
  canWrite: Record<string, boolean>,
  archived = false
) => {
  const api = {
    list: vi.fn().mockResolvedValue(defs),
    values: vi.fn().mockResolvedValue({ values, can_write: canWrite }),
    setValue: vi.fn(),
  } as unknown as TPropertiesApi & { setValue: ReturnType<typeof vi.fn> };
  holder.store = new PropertiesStore(api);
  const view = render(<ItemCustomProperties workspaceSlug="acme" projectId="p1" issueId="i1" archived={archived} />);
  return { api, view };
};

describe("ItemCustomProperties", () => {
  it("leaves hidden properties out", async () => {
    setup(
      [prop({ key: "customer", name: "Customer" }), prop({ key: "secret", name: "Secret", visible: false })],
      { customer: "Acme", secret: "x" },
      { customer: true, secret: true }
    );
    expect(await screen.findByText("Customer")).toBeTruthy();
    expect(screen.queryByText("Secret")).toBeNull();
  });

  it("shows a read-only value with a lock", async () => {
    setup([prop({ key: "verdict", name: "Verdict", write_role: 20 })], { verdict: "ok" }, { verdict: false });
    expect(await screen.findByLabelText("Only admins can change this")).toBeTruthy();
    await userEvent.click(screen.getByText("ok"));
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("rolls back a refused save and toasts the server's reason", async () => {
    const { api } = setup([prop({ key: "customer", name: "Customer" })], { customer: "Acme" }, { customer: true });
    api.setValue.mockRejectedValue({ custom_fields: { customer: "too long" } });
    await userEvent.click(await screen.findByText("Acme"));
    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), "Beta{Enter}");
    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith({ type: "error", title: "Couldn't save Customer", message: "too long" })
    );
    expect(screen.getByText("Acme")).toBeTruthy();
  });

  it("lets a guest edit a property the server says they can write", async () => {
    setup([prop({ key: "mood", name: "Mood", write_role: 5 })], { mood: "ok" }, { mood: true });
    await userEvent.click(await screen.findByText("ok"));
    expect(screen.getByRole("textbox")).toBeTruthy();
  });

  it("keeps an archived item read-only", async () => {
    setup([prop({ key: "mood", name: "Mood" })], { mood: "ok" }, { mood: true }, true);
    await userEvent.click(await screen.findByText("ok"));
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("renders nothing without visible properties", async () => {
    const { api, view } = setup([prop({ visible: false })], {}, {});
    await waitFor(() => expect(api.values).toHaveBeenCalled());
    expect(view.container.innerHTML).toBe("");
  });
});
