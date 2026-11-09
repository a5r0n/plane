/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { sortBy } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
// local imports
import { sameValue } from "./helpers";
import type { TPropertiesApi } from "./service";
import type { TItemFields, TProperty, TPropertyInput, TValue } from "./types";

type TProjectRef = { slug: string; projectId: string };
type TItemRef = TProjectRef & { issueId: string };

const sorted = (defs: TProperty[]) => sortBy(defs, "sort_order");

/** Each project's property definitions and each item's values, with optimistic writes that roll back. */
export class PropertiesStore {
  byProject: Record<string, TProperty[]> = {};
  byIssue: Record<string, TItemFields> = {};

  constructor(private api: TPropertiesApi) {
    makeObservable(this, {
      byProject: observable,
      byIssue: observable,
      fetchDefinitions: action,
      fetchValues: action,
      setValue: action,
      createDefinition: action,
      updateDefinition: action,
      removeDefinition: action,
      reorder: action,
    });
  }

  definitions = (projectId: string): TProperty[] | undefined => this.byProject[projectId];

  private setDefs(projectId: string, defs: TProperty[]) {
    runInAction(() => {
      this.byProject[projectId] = sorted(defs);
    });
  }

  private setFields(issueId: string, fields: TItemFields) {
    runInAction(() => {
      this.byIssue[issueId] = fields;
    });
  }

  // Apply now, call the server, roll back if it refuses.
  private async optimistic<T>(apply: () => void, undo: () => void, call: () => Promise<T>): Promise<T> {
    apply();
    try {
      return await call();
    } catch (error) {
      undo();
      throw error;
    }
  }

  private async optimisticDefs<T>(projectId: string, next: TProperty[], call: () => Promise<T>): Promise<T> {
    const before = this.byProject[projectId] ?? [];
    return this.optimistic(
      () => this.setDefs(projectId, next),
      () => this.setDefs(projectId, before),
      call
    );
  }

  fetchDefinitions = async ({ slug, projectId }: TProjectRef) => {
    const defs = await this.api.list(slug, projectId);
    this.setDefs(projectId, defs);
    return this.byProject[projectId];
  };

  fetchValues = async ({ slug, projectId, issueId }: TItemRef) => {
    const fields = await this.api.values(slug, projectId, issueId);
    this.setFields(issueId, fields);
    return fields;
  };

  setValue = async ({ slug, projectId, issueId }: TItemRef, key: string, value: TValue) => {
    const before = this.byIssue[issueId];
    if (before && sameValue(before.values[key], value)) return;
    const next = before ? { ...before, values: { ...before.values, [key]: value } } : undefined;
    const saved = await this.optimistic(
      () => next && this.setFields(issueId, next),
      () => before && this.setFields(issueId, before),
      () => this.api.setValue(slug, projectId, issueId, key, value)
    );
    this.setFields(issueId, saved);
  };

  createDefinition = async ({ slug, projectId }: TProjectRef, data: TPropertyInput) => {
    const created = await this.api.create(slug, projectId, data);
    this.setDefs(projectId, [...(this.byProject[projectId] ?? []), created]);
    return created;
  };

  updateDefinition = async ({ slug, projectId }: TProjectRef, id: string, data: TPropertyInput) => {
    const next = (this.byProject[projectId] ?? []).map((def) => (def.id === id ? Object.assign({}, def, data) : def));
    const saved = await this.optimisticDefs(projectId, next, () => this.api.update(slug, projectId, id, data));
    this.setDefs(
      projectId,
      (this.byProject[projectId] ?? []).map((def) => (def.id === id ? saved : def))
    );
    return saved;
  };

  removeDefinition = async ({ slug, projectId }: TProjectRef, id: string) => {
    const next = (this.byProject[projectId] ?? []).filter((def) => def.id !== id);
    await this.optimisticDefs(projectId, next, () => this.api.remove(slug, projectId, id));
  };

  reorder = (ref: TProjectRef, id: string, sortOrder: number) =>
    this.updateDefinition(ref, id, { sort_order: sortOrder });
}
