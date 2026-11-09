/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";
// local imports
import type { TItemFields, TProperty, TPropertyInput, TValue } from "./types";

export type TPropertiesApi = {
  list(slug: string, projectId: string): Promise<TProperty[]>;
  create(slug: string, projectId: string, data: TPropertyInput): Promise<TProperty>;
  update(slug: string, projectId: string, id: string, data: TPropertyInput): Promise<TProperty>;
  remove(slug: string, projectId: string, id: string): Promise<void>;
  values(slug: string, projectId: string, issueId: string): Promise<TItemFields>;
  setValue(slug: string, projectId: string, issueId: string, key: string, value: TValue): Promise<TItemFields>;
};

// Session routes from plane/ext (the v1 ones take an API key).
export class PropertiesService extends APIService implements TPropertiesApi {
  constructor() {
    super(API_BASE_URL);
  }

  private url(slug: string, projectId: string, tail = "") {
    return `/api/workspaces/${slug}/projects/${projectId}/${tail}`;
  }

  private unwrap<T>(request: Promise<{ data: T }>): Promise<T> {
    return request
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  list(slug: string, projectId: string) {
    return this.unwrap<TProperty[]>(this.get(this.url(slug, projectId, "properties/")));
  }

  create(slug: string, projectId: string, data: TPropertyInput) {
    return this.unwrap<TProperty>(this.post(this.url(slug, projectId, "properties/"), data));
  }

  update(slug: string, projectId: string, id: string, data: TPropertyInput) {
    return this.unwrap<TProperty>(this.patch(this.url(slug, projectId, `properties/${id}/`), data));
  }

  remove(slug: string, projectId: string, id: string) {
    return this.unwrap<void>(this.delete(this.url(slug, projectId, `properties/${id}/`)));
  }

  values(slug: string, projectId: string, issueId: string) {
    return this.unwrap<TItemFields>(this.get(this.url(slug, projectId, `issues/${issueId}/custom-fields/`)));
  }

  setValue(slug: string, projectId: string, issueId: string, key: string, value: TValue) {
    return this.unwrap<TItemFields>(
      this.patch(this.url(slug, projectId, `issues/${issueId}/custom-fields/`), { [key]: value })
    );
  }
}
