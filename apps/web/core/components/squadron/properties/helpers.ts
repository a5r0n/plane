/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { format } from "date-fns";
import { sortBy } from "lodash-es";
// local imports
import type { TProperty, TValue, TWriteRole } from "./types";

const isEmpty = (value: TValue | undefined) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

/** The properties an item shows, in settings order. */
export const visibleSorted = (defs: TProperty[]): TProperty[] =>
  sortBy(
    defs.filter((def) => def.visible),
    "sort_order"
  );

const formatOne = (prop: TProperty, value: string | number | boolean, memberName: (id: string) => string) => {
  switch (prop.type) {
    case "number":
      return String(Number(value));
    case "boolean":
      return value ? "Yes" : "No";
    case "date": {
      const [y, m, d] = String(value).split("-").map(Number);
      return format(new Date(y, m - 1, d), "MMM d, yyyy");
    }
    case "datetime":
      return format(new Date(String(value)), "MMM d, yyyy, HH:mm");
    case "choice":
      return prop.options.find((option) => option.id === value)?.label ?? String(value);
    case "member":
      return memberName(String(value));
    default:
      return String(value);
  }
};

/** A value as text; null when unset. */
export const formatValue = (
  prop: TProperty,
  value: TValue | undefined,
  memberName: (id: string) => string = (id) => id
): string | null => {
  if (isEmpty(value)) return null;
  const items = Array.isArray(value) ? value : [value as string | number | boolean];
  return items.map((item) => formatOne(prop, item, memberName)).join(", ");
};

/** Whether saving `b` over `a` changes nothing (empty text is the same as unset). */
export const sameValue = (a: TValue | undefined, b: TValue | undefined): boolean => {
  if (isEmpty(a) || isEmpty(b)) return isEmpty(a) && isEmpty(b);
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((item, i) => item === b[i]);
  }
  return a === b;
};

/** A property key from its name: lowercase, underscores, starting with a letter, at most 64 long. */
export const slugKey = (name: string): string => {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return (/^[a-z]/.test(slug) ? slug : `p_${slug}`).slice(0, 64).replace(/_+$/, "");
};

export const lockText = (writeRole: TWriteRole): string =>
  writeRole === 20 ? "Only admins can change this" : "Only members and admins can change this";

const firstString = (body: unknown): string | undefined => {
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map(firstString).find(Boolean);
  if (body && typeof body === "object") return Object.values(body).map(firstString).find(Boolean);
  return undefined;
};

/** The server's reason for refusing a write. */
export const errorText = (error: unknown, key?: string): string => {
  const body = (error ?? {}) as { custom_fields?: Record<string, string> | string; error?: string };
  const fields = body.custom_fields;
  if (key && fields && typeof fields === "object" && typeof fields[key] === "string") return fields[key];
  if (typeof body.error === "string") return body.error;
  return firstString(error) ?? "Couldn't save the change";
};
