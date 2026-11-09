/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { LucideIcon } from "lucide-react";
import { Calendar, CalendarClock, Hash, Link, ListChecks, ToggleLeft, Type, User } from "lucide-react";
import type { TPropertyType } from "./types";

export const PROPERTY_ICONS: Record<TPropertyType, LucideIcon> = {
  text: Type,
  number: Hash,
  boolean: ToggleLeft,
  date: Calendar,
  datetime: CalendarClock,
  choice: ListChecks,
  member: User,
  url: Link,
};
