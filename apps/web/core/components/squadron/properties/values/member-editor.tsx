/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import type { TProperty, TValue } from "../types";

type Props = { prop: TProperty; value: TValue; projectId: string; onChange: (value: TValue) => void };

const common = (prop: TProperty) => ({
  placeholder: `Add ${prop.name}`,
  buttonVariant: "transparent-with-text" as const,
  className: "group w-full grow",
  buttonContainerClassName: "w-full text-left h-7.5",
  buttonClassName: "text-13 justify-between",
  hideIcon: false,
});

export function MemberEditor({ prop, value, projectId, onChange }: Props) {
  if (prop.multiple)
    return (
      <MemberDropdown
        {...common(prop)}
        projectId={projectId}
        multiple
        value={Array.isArray(value) ? value : []}
        onChange={(ids: string[]) => onChange(ids.length ? ids : null)}
      />
    );
  return (
    <MemberDropdown
      {...common(prop)}
      projectId={projectId}
      multiple={false}
      value={typeof value === "string" ? value : null}
      onChange={(id: string | null) => onChange(id)}
    />
  );
}
