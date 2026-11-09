/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const rows = vi.hoisted(() => ({}) as Record<string, object>);
const defs = vi.hoisted(() => ({}) as Record<string, object[]>);

vi.mock("@/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block", () => ({
  IssueActivityBlockComponent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/hooks/store/use-issue-detail", () => ({
  useIssueDetail: () => ({ activity: { getActivityById: (id: string) => rows[id] } }),
}));

vi.mock("../use-properties", () => ({
  useProperties: () => ({ definitions: (projectId: string) => defs[projectId] }),
}));

const { IssuePropertyActivity } = await import("../activity-property");
const { formatValue } = await import("../helpers");

afterEach(cleanup);

const row = (project: string, old_value: string | null, new_value: string | null) => ({
  field: "custom_fields",
  comment: "updated Due",
  project,
  new_identifier: "p-due",
  old_value,
  new_value,
});

describe("IssuePropertyActivity", () => {
  it("reads as a change with the property's name in bold", () => {
    rows.a1 = { field: "custom_fields", comment: "updated Story points", old_value: "2", new_value: "3" };
    const { container } = render(<IssuePropertyActivity activityId="a1" ends={undefined} />);
    expect(container.textContent).toBe("changed Story points from 2 to 3");
    expect(container.querySelector(".font-medium")?.textContent).toBe("Story points");
  });

  it("reads set and cleared", () => {
    rows.a2 = { comment: "updated Repo", old_value: null, new_value: "plane" };
    rows.a3 = { comment: "updated Owner", old_value: "Ann", new_value: null };
    expect(render(<IssuePropertyActivity activityId="a2" ends={undefined} />).container.textContent).toBe(
      "set Repo to plane"
    );
    expect(render(<IssuePropertyActivity activityId="a3" ends={undefined} />).container.textContent).toBe(
      "cleared Owner"
    );
  });

  describe("datetime values", () => {
    const due = { id: "p-due", key: "due", name: "Due", type: "datetime", options: [] };
    const from = "2026-11-09T14:30:00+00:00";
    const to = "2026-11-12T07:00:00Z";
    const text = (id: string) =>
      render(<IssuePropertyActivity activityId={id} ends={undefined} />).container.textContent;

    it("formats them when the definition is loaded", () => {
      defs.p1 = [due];
      rows.d1 = row("p1", from, to);
      const show = (iso: string) => formatValue(due as never, iso);
      expect(show(from)).not.toBe(from);
      expect(text("d1")).toBe(`changed Due from ${show(from)} to ${show(to)}`);
    });

    it("keeps the raw text when the definition isn't loaded", () => {
      rows.d2 = row("p-unloaded", null, to);
      expect(text("d2")).toBe(`set Due to ${to}`);
    });

    it("keeps the raw text when the value isn't a date", () => {
      defs.p1 = [due];
      rows.d3 = row("p1", null, "soon");
      expect(text("d3")).toBe("set Due to soon");
    });
  });
});
