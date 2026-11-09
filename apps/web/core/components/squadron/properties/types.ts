/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TPropertyType = "text" | "number" | "boolean" | "date" | "datetime" | "choice" | "member" | "url";

export type TOption = { id?: string; label: string; disabled: boolean };

export type TWriteRole = 5 | 15 | 20;

export type TProperty = {
  id: string;
  name: string;
  key: string;
  type: TPropertyType;
  description: string;
  options: TOption[];
  multiple: boolean;
  visible: boolean;
  write_role: TWriteRole;
  sort_order: number;
};

export type TPropertyInput = Partial<Omit<TProperty, "id">>;

// number, ISO date/datetime text, option id(s), member id(s), or null when unset
export type TValue = string | number | boolean | null | string[];

export type TItemFields = { values: Record<string, TValue>; can_write: Record<string, boolean> };
