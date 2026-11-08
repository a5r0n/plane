/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import type { TStep, TStepInput } from "../types";

export type TActor = { id: string; name: string; avatarUrl?: string; isBot: boolean };

export type TStepHandlers = {
  add(data: TStepInput, position: number): Promise<unknown>;
  update(stepId: string, data: TStepInput): Promise<unknown>;
  remove(stepId: string): Promise<unknown>;
  reorder(steps: TStep[]): Promise<unknown>;
};

export type TActorPicker = (value: string | null, onChange: (actor: string | null) => void) => ReactNode;

export type TOutcome = "done" | "failed";
