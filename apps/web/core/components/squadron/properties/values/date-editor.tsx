/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { format } from "date-fns";
import { DateDropdown } from "@/components/dropdowns/date";
import { renderFormattedPayloadDate } from "@plane/utils";
import type { TProperty, TValue } from "../types";

type Props = { prop: TProperty; value: TValue; onChange: (value: TValue) => void };

/** Combines a local date and "HH:mm" into an ISO instant. */
const combine = (date: Date, time: string): string => {
  const [h, m] = (time || "00:00").split(":").map(Number);
  const local = new Date(date.getFullYear(), date.getMonth(), date.getDate(), h, m);
  return local.toISOString();
};

const parseDate = (text: string): Date => {
  const [y, m, d] = text.split("-").map(Number);
  return new Date(y, m - 1, d);
};

export function DateEditor({ prop, value, onChange }: Props) {
  const text = typeof value === "string" ? value : null;
  const current = text ? (prop.type === "datetime" ? new Date(text) : parseDate(text)) : null;
  const time = current && prop.type === "datetime" ? format(current, "HH:mm") : "";

  const pickDate = (date: Date | null) => {
    if (!date) return onChange(null);
    if (prop.type === "date") return onChange(renderFormattedPayloadDate(date) ?? null);
    onChange(combine(date, time));
  };

  return (
    <div className="flex w-full items-center gap-1">
      <DateDropdown
        value={current}
        onChange={pickDate}
        placeholder={`Add ${prop.name}`}
        buttonVariant="transparent-with-text"
        className="group w-full grow"
        buttonContainerClassName="w-full text-left h-7.5"
        buttonClassName={`text-13 ${current ? "" : "text-placeholder"}`}
        hideIcon
        clearIconClassName="h-3 w-3 hidden group-hover:inline"
        isClearable
      />
      {prop.type === "datetime" && current && (
        <input
          type="time"
          aria-label={`${prop.name} time`}
          className="h-7.5 shrink-0 rounded-sm bg-transparent px-1 text-13 text-secondary outline-none hover:bg-layer-1"
          value={time}
          onChange={(e) => onChange(combine(current, e.target.value))}
        />
      )}
    </div>
  );
}
