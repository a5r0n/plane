/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { action, makeObservable, observable, runInAction } from "mobx";
// local imports
import { summarize } from "./helpers";
import type { TStepsApi } from "./service";
import type { TStep, TStepInput, TStepSummary } from "./types";

type TRef = { slug: string; projectId: string; issueId: string };

/** Each work item's path, with optimistic writes that roll back on failure. */
export class StepsStore {
  stepsByIssue: Record<string, TStep[]> = {};
  // Items whose panel has an editor open for a new step (from "Add steps").
  adding: Record<string, boolean> = {};

  constructor(
    private api: TStepsApi,
    private onSummary: (issueId: string, summary: TStepSummary | null) => void = () => {}
  ) {
    makeObservable(this, {
      stepsByIssue: observable,
      adding: observable,
      setAdding: action,
      fetch: action,
      add: action,
      update: action,
      remove: action,
      reorder: action,
    });
  }

  setAdding = (issueId: string, value: boolean) => {
    this.adding[issueId] = value;
  };

  steps = (issueId: string): TStep[] | undefined => this.stepsByIssue[issueId];

  private set(issueId: string, steps: TStep[]) {
    runInAction(() => {
      this.stepsByIssue[issueId] = steps;
    });
    this.onSummary(issueId, summarize(steps));
  }

  // Apply now, call the server, roll back if it refuses.
  private async optimistic<T>(issueId: string, next: TStep[], call: () => Promise<T>): Promise<T> {
    const before = this.stepsByIssue[issueId] ?? [];
    this.set(issueId, next);
    try {
      return await call();
    } catch (error) {
      this.set(issueId, before);
      throw error;
    }
  }

  fetch = async ({ slug, projectId, issueId }: TRef) => {
    const steps = await this.api.list(slug, projectId, issueId);
    this.set(issueId, steps);
    return steps;
  };

  add = async ({ slug, projectId, issueId }: TRef, data: TStepInput, position?: number) => {
    const step = await this.api.create(slug, projectId, issueId, { ...data, position });
    const steps = [...(this.stepsByIssue[issueId] ?? [])];
    steps.splice(position ?? steps.length, 0, step);
    this.set(issueId, steps);
    return step;
  };

  update = async ({ slug, projectId, issueId }: TRef, stepId: string, data: TStepInput) => {
    const steps = this.stepsByIssue[issueId] ?? [];
    const next = steps.map((step) => (step.id === stepId ? Object.assign({}, step, data) : step));
    const saved = await this.optimistic(issueId, next, () => this.api.update(slug, projectId, issueId, stepId, data));
    this.set(
      issueId,
      (this.stepsByIssue[issueId] ?? []).map((step) => (step.id === stepId ? saved : step))
    );
    return saved;
  };

  remove = async ({ slug, projectId, issueId }: TRef, stepId: string) => {
    const next = (this.stepsByIssue[issueId] ?? []).filter((step) => step.id !== stepId);
    await this.optimistic(issueId, next, () => this.api.remove(slug, projectId, issueId, stepId));
  };

  reorder = async ({ slug, projectId, issueId }: TRef, ordered: TStep[]) => {
    const saved = await this.optimistic(issueId, ordered, () =>
      this.api.reorder(
        slug,
        projectId,
        issueId,
        ordered.map((step) => step.id)
      )
    );
    this.set(issueId, saved);
  };
}
