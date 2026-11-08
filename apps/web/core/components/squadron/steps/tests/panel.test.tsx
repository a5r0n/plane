/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StepsStore } from "../store";
import { step } from "./fixtures";

const state = vi.hoisted(() => ({ store: undefined as unknown }));
vi.mock("../use-steps", () => ({ useSteps: () => state.store }));
vi.mock("@/hooks/store/use-member", () => ({ useMember: () => ({ getUserDetails: () => undefined }) }));
vi.mock("@/hooks/store/user", () => ({ useUser: () => ({ data: { id: "me" } }) }));
vi.mock("@/components/dropdowns/member/dropdown", () => ({ MemberDropdown: () => null }));
vi.mock("@/components/issues/issue-detail-widgets/widget-button", () => ({ IssueDetailWidgetButton: () => null }));

const { StepsPanel } = await import("../panel");

const storeWith = (steps: ReturnType<typeof step>[]) =>
  new StepsStore({
    list: vi.fn().mockResolvedValue(steps),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    reorder: vi.fn(),
  });

beforeEach(() => {
  window.matchMedia = vi
    .fn()
    .mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
});
afterEach(cleanup);

const panel = () => <StepsPanel workspaceSlug="acme" projectId="p1" issueId="i1" disabled={false} />;

describe("StepsPanel", () => {
  it("shows nothing for an item without steps", async () => {
    const store = storeWith([]);
    state.store = store;
    const { container } = render(panel());
    await vi.waitFor(() => expect(store.steps("i1")).toEqual([]));
    expect(container.innerHTML).toBe("");
  });

  it("shows the progress header and the your-turn bar when it's the viewer's step", async () => {
    state.store = storeWith([step({ status: "done" }), step({ title: "review", actor: "me" })]);
    render(panel());
    expect(await screen.findByText(/1\/2 done/)).toBeTruthy();
    expect(screen.getByText("Your turn: review")).toBeTruthy();
  });

  it("hides the your-turn bar when the current step is someone else's", async () => {
    state.store = storeWith([step({ title: "review", actor: "you" })]);
    render(panel());
    await screen.findByText(/0\/1 done/);
    expect(screen.queryByText(/Your turn/)).toBeNull();
  });
});
