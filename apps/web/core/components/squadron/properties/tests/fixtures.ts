/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TProperty } from "../types";

let n = 0;
export const prop = (over: Partial<TProperty> = {}): TProperty => {
  n += 1;
  return {
    id: `p${n}`,
    name: `Prop ${n}`,
    key: `prop_${n}`,
    type: "text",
    description: "",
    options: [],
    multiple: false,
    visible: true,
    write_role: 15,
    sort_order: n,
    ...over,
  };
};

export const choice = (over: Partial<TProperty> = {}): TProperty =>
  prop({
    type: "choice",
    options: [
      { id: "a", label: "Alpha", disabled: false },
      { id: "b", label: "Beta", disabled: false },
    ],
    ...over,
  });
