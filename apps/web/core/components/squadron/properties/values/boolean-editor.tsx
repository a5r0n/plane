/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ToggleSwitch } from "@plane/ui";
import type { TProperty, TValue } from "../types";

type Props = { prop: TProperty; value: TValue; onChange: (value: TValue) => void };

export function BooleanEditor({ prop, value, onChange }: Props) {
  return (
    <div className="flex h-7.5 items-center px-2">
      <ToggleSwitch value={value === true} label={prop.name} onChange={(next) => onChange(next)} />
    </div>
  );
}
