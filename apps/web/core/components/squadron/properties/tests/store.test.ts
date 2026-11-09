/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it, vi } from "vitest";
import type { TPropertiesApi } from "../service";
import { PropertiesStore } from "../store";
import type { TItemFields } from "../types";
import { prop } from "./fixtures";

const ref = { slug: "acme", projectId: "p1", issueId: "i1" };
const fields = (values: TItemFields["values"]): TItemFields => ({
  values,
  can_write: Object.fromEntries(Object.keys(values).map((key) => [key, true])),
});

const api = (over: Partial<TPropertiesApi> = {}): TPropertiesApi => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  values: vi.fn().mockResolvedValue(fields({ repo: "old", points: 2 })),
  setValue: vi.fn(),
  ...over,
});

describe("PropertiesStore values", () => {
  it("applies a value at once and keeps the server's copy", async () => {
    let resolve!: (value: TItemFields) => void;
    const store = new PropertiesStore(api({ setValue: vi.fn(() => new Promise<TItemFields>((r) => (resolve = r))) }));
    await store.fetchValues(ref);
    const pending = store.setValue(ref, "repo", "new");
    expect(store.byIssue.i1.values.repo).toBe("new");
    resolve(fields({ repo: "new", points: 5 }));
    await pending;
    expect(store.byIssue.i1.values.points).toBe(5);
  });

  it("restores the old value and rethrows when refused", async () => {
    const refusal = { custom_fields: { repo: "expects one of…" } };
    const store = new PropertiesStore(api({ setValue: vi.fn().mockRejectedValue(refusal) }));
    await store.fetchValues(ref);
    await expect(store.setValue(ref, "repo", "bad")).rejects.toEqual(refusal);
    expect(store.byIssue.i1.values.repo).toBe("old");
  });

  it("sends nothing for an unchanged value", async () => {
    const setValue = vi.fn();
    const store = new PropertiesStore(api({ setValue }));
    await store.fetchValues(ref);
    await store.setValue(ref, "repo", "old");
    expect(setValue).not.toHaveBeenCalled();
  });

  it("clears with null", async () => {
    const setValue = vi.fn().mockResolvedValue(fields({ repo: null, points: 2 }));
    const store = new PropertiesStore(api({ setValue }));
    await store.fetchValues(ref);
    await store.setValue(ref, "repo", null);
    expect(setValue).toHaveBeenCalledWith("acme", "p1", "i1", "repo", null);
    expect(store.byIssue.i1.values.repo).toBeNull();
  });
});

describe("PropertiesStore definitions", () => {
  const pref = { slug: "acme", projectId: "p1" };

  it("lists sorted and rolls back a refused delete", async () => {
    const [a, b] = [prop({ sort_order: 2 }), prop({ sort_order: 1 })];
    const store = new PropertiesStore(
      api({ list: vi.fn().mockResolvedValue([a, b]), remove: vi.fn().mockRejectedValue({ error: "no" }) })
    );
    await store.fetchDefinitions(pref);
    expect(store.definitions("p1")).toEqual([b, a]);
    await expect(store.removeDefinition(pref, a.id)).rejects.toEqual({ error: "no" });
    expect(store.definitions("p1")).toEqual([b, a]);
  });

  it("reorders optimistically and keeps the server's copy", async () => {
    const [a, b] = [prop({ sort_order: 1 }), prop({ sort_order: 2 })];
    const update = vi.fn().mockResolvedValue({ ...a, sort_order: 3 });
    const store = new PropertiesStore(api({ list: vi.fn().mockResolvedValue([a, b]), update }));
    await store.fetchDefinitions(pref);
    await store.reorder(pref, [{ id: a.id, sort_order: 3 }]);
    expect(update).toHaveBeenCalledWith("acme", "p1", a.id, { sort_order: 3 });
    expect(store.definitions("p1")?.map((p) => p.id)).toEqual([b.id, a.id]);
  });

  it("adds a created definition", async () => {
    const created = prop();
    const store = new PropertiesStore(
      api({ list: vi.fn().mockResolvedValue([]), create: vi.fn().mockResolvedValue(created) })
    );
    await store.fetchDefinitions(pref);
    await store.createDefinition(pref, { name: created.name });
    expect(store.definitions("p1")).toEqual([created]);
  });
});
