/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useIssueDetail } from "@/hooks/store/use-issue-detail";

/** Whether the work item in the detail store is an epic (the backend marks `is_epic`). */
export function useIsEpic(issueId: string | undefined): boolean {
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  return !!(issueId && getIssueById(issueId)?.is_epic);
}
