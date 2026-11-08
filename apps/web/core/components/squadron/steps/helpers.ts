/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TCurrentStep, TStep, TStepSummary, TStepTone } from "./types";

export const isOpen = (step: Pick<TStep, "status">) => step.status === "pending" || step.status === "failed";

/** The first pending or failed step; a failed one holds the path. */
export const currentStep = <T extends Pick<TStep, "status">>(steps: T[]): T | undefined => steps.find(isOpen);

export const isWaiting = (step: Pick<TStep, "not_before">, now: Date = new Date()) =>
  !!step.not_before && new Date(step.not_before).getTime() > now.getTime();

/** Red beats amber; a future not_before reads grey even on the viewer's turn. */
export const stepTone = (
  step: TCurrentStep | undefined | null,
  viewerId: string | undefined,
  now?: Date
): TStepTone => {
  if (!step) return "neutral";
  if (step.status === "failed") return "failed";
  if (isWaiting(step, now)) return "waiting";
  if (viewerId && step.actor === viewerId) return "turn";
  return "neutral";
};

/** Done and skipped both count as done. */
export const summarize = (steps: TStep[]): TStepSummary | null => {
  if (steps.length === 0) return null;
  const current = currentStep(steps);
  return {
    done: steps.filter((step) => !isOpen(step)).length,
    total: steps.length,
    current: current
      ? {
          id: current.id,
          title: current.title,
          status: current.status,
          not_before: current.not_before,
          actor: current.actor,
        }
      : null,
  };
};

/** Swap a step with its neighbour; returns the new order, or the same array at an edge. */
export const moveStep = <T extends { id: string }>(steps: T[], id: string, by: -1 | 1): T[] => {
  const from = steps.findIndex((step) => step.id === id);
  const to = from + by;
  if (from < 0 || to < 0 || to >= steps.length) return steps;
  const next = [...steps];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
};

export const TONE_CLASSES: Record<TStepTone, string> = {
  turn: "bg-warning-subtle text-warning-primary border-warning-primary",
  failed: "bg-danger-subtle text-danger-primary border-danger-strong",
  waiting: "bg-layer-1 text-tertiary border-subtle",
  neutral: "bg-layer-1 text-secondary border-subtle",
};

export const formatWhen = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/** ISO string to a datetime-local input value, in local time. */
export const toLocalInput = (iso: string | null) => {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

export const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

/** Stable callback ref: focuses an editor once, when it mounts. */
export const focusOnMount = (el: HTMLElement | null) => el?.focus();
