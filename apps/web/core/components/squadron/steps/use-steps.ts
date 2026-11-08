/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssue } from "@plane/types";
import { rootStore } from "@/lib/store-context";
// local imports
import { StepsService } from "./service";
import { StepsStore } from "./store";

let store: StepsStore | undefined;

/** The steps store; each write also refreshes the item's `step_summary` for list chips. */
export const useSteps = (): StepsStore => {
  store ??= new StepsStore(new StepsService(), (issueId, summary) =>
    rootStore.issue.issues.updateIssue(issueId, { step_summary: summary } as Partial<TIssue>)
  );
  return store;
};
