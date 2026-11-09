/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const rows = vi.hoisted(() => ({}) as Record<string, object>);

vi.mock("@/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block", () => ({
  IssueActivityBlockComponent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/hooks/store/use-issue-detail", () => ({
  useIssueDetail: () => ({ activity: { getActivityById: (id: string) => rows[id] } }),
}));

const { IssuePropertyActivity } = await import("../activity-property");

afterEach(cleanup);

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
});
