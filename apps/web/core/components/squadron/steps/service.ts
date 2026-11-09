/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";
// local imports
import type { TStep, TStepInput } from "./types";

export type TStepsApi = {
  list(slug: string, projectId: string, issueId: string): Promise<TStep[]>;
  create(slug: string, projectId: string, issueId: string, data: TStepInput & { position?: number }): Promise<TStep>;
  update(slug: string, projectId: string, issueId: string, stepId: string, data: TStepInput): Promise<TStep>;
  remove(slug: string, projectId: string, issueId: string, stepId: string): Promise<void>;
  reorder(slug: string, projectId: string, issueId: string, stepIds: string[]): Promise<TStep[]>;
};

// Session routes from plane/ext (the v1 ones take an API key).
export class StepsService extends APIService implements TStepsApi {
  constructor() {
    super(API_BASE_URL);
  }

  private url(slug: string, projectId: string, issueId: string, tail = "") {
    return `/api/workspaces/${slug}/projects/${projectId}/issues/${issueId}/steps/${tail}`;
  }

  private unwrap<T>(request: Promise<{ data: T }>): Promise<T> {
    return request
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  list(slug: string, projectId: string, issueId: string) {
    return this.unwrap<TStep[]>(this.get(this.url(slug, projectId, issueId)));
  }

  create(slug: string, projectId: string, issueId: string, data: TStepInput & { position?: number }) {
    return this.unwrap<TStep>(this.post(this.url(slug, projectId, issueId), data));
  }

  update(slug: string, projectId: string, issueId: string, stepId: string, data: TStepInput) {
    return this.unwrap<TStep>(this.patch(this.url(slug, projectId, issueId, `${stepId}/`), data));
  }

  remove(slug: string, projectId: string, issueId: string, stepId: string) {
    return this.unwrap<void>(this.delete(this.url(slug, projectId, issueId, `${stepId}/`)));
  }

  reorder(slug: string, projectId: string, issueId: string, stepIds: string[]) {
    return this.unwrap<TStep[]>(this.post(this.url(slug, projectId, issueId, "reorder/"), { step_ids: stepIds }));
  }
}
