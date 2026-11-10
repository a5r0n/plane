/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { StrictMode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { action, observable } from "mobx";
import { afterEach, describe, expect, it, vi } from "vitest";

// Same toggle as upstream's SubIssuesStore.setSubIssueHelpers.
const helpers = observable.map<string, Record<string, string[]>>();
const setSubIssueHelpers = action((id: string, key: string, value: string) => {
  if (!id || !key || !value) return;
  const entry = helpers.get(id) ?? { preview_loader: [], issue_visibility: [], issue_loader: [] };
  const list = entry[key] ?? [];
  helpers.set(id, { ...entry, [key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value] });
});
const subIssueHelpersByIssueId = (id: string) => ({
  preview_loader: helpers.get(id)?.preview_loader ?? [],
  issue_visibility: helpers.get(id)?.issue_visibility ?? [],
  issue_loader: helpers.get(id)?.issue_loader ?? [],
});
const fetchSubIssues = vi.fn(() => Promise.resolve());

vi.mock("@/hooks/store/use-issue-detail", () => ({
  useIssueDetail: () => ({
    toggleCreateIssueModal: vi.fn(),
    toggleDeleteIssueModal: vi.fn(),
    subIssues: { subIssueHelpersByIssueId, setSubIssueHelpers },
  }),
}));
vi.mock("@/components/issues/issue-detail-widgets/sub-issues/helper", () => ({
  useSubIssueOperations: () => ({ fetchSubIssues }),
}));
vi.mock("@/components/issues/issue-detail-widgets/sub-issues/issues-list/root", () => ({
  SubIssuesListRoot: () => <div>sub-issues list</div>,
}));
vi.mock("@/components/issues/delete-issue-modal", () => ({ DeleteIssueModal: () => null }));
vi.mock("@/components/issues/issue-modal/modal", () => ({ CreateUpdateIssueModal: () => null }));

const { SubIssuesCollapsibleContent } = await import("@/components/issues/issue-detail-widgets/sub-issues/content");

afterEach(() => {
  cleanup();
  helpers.clear();
});

describe("SubIssuesCollapsibleContent", () => {
  it("shows the sub-work items list under StrictMode's double effect", async () => {
    render(
      <StrictMode>
        <SubIssuesCollapsibleContent workspaceSlug="acme" projectId="p1" parentIssueId="i1" disabled={false} />
      </StrictMode>
    );
    await vi.waitFor(() => expect(fetchSubIssues).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("sub-issues list")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText("sub-issues list")).toBeTruthy();
  });
});
