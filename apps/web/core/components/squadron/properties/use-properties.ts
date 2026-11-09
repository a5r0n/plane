/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// local imports
import { PropertiesService } from "./service";
import { PropertiesStore } from "./store";

let store: PropertiesStore | undefined;

/** The custom properties store, shared by the item page, peek and settings. */
export const useProperties = (): PropertiesStore => {
  store ??= new PropertiesStore(new PropertiesService());
  return store;
};
