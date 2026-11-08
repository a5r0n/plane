/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TStep } from "../types";

let n = 0;
export const step = (over: Partial<TStep> = {}): TStep => {
  n += 1;
  return {
    id: `s${n}`,
    issue: "i1",
    title: `step ${n}`,
    detail: "",
    actor: null,
    status: "pending",
    note: "",
    sort_order: n,
    not_before: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...over,
  };
};

export const FUTURE = "2999-01-01T00:00:00Z";
export const PAST = "2000-01-01T00:00:00Z";
