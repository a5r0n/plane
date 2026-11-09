/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it, vi } from "vitest";
import type { TStepsApi } from "../service";
import { StepsStore } from "../store";
import { step } from "./fixtures";

const ref = { slug: "acme", projectId: "p1", issueId: "i1" };

const api = (over: Partial<TStepsApi> = {}): TStepsApi => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  reorder: vi.fn(),
  ...over,
});

describe("StepsStore", () => {
  it("applies a finish at once and keeps the server's copy", async () => {
    const a = step();
    const saved = { ...a, status: "done" as const, note: "ok" };
    let resolve!: (value: typeof saved) => void;
    const store = new StepsStore(
      api({
        list: vi.fn().mockResolvedValue([a]),
        update: vi.fn(() => new Promise<typeof saved>((r) => (resolve = r))),
      })
    );
    await store.fetch(ref);
    const pending = store.update(ref, a.id, { status: "done" });
    expect(store.steps("i1")?.[0].status).toBe("done");
    resolve(saved);
    await pending;
    expect(store.steps("i1")?.[0].note).toBe("ok");
  });

  it("rolls back a refused update and reorder, and refreshes the summary each time", async () => {
    const [a, b] = [step(), step()];
    const onSummary = vi.fn();
    const store = new StepsStore(
      api({
        list: vi.fn().mockResolvedValue([a, b]),
        update: vi.fn().mockRejectedValue({ error: "no" }),
        reorder: vi.fn().mockRejectedValue({ error: "no" }),
      }),
      onSummary
    );
    await store.fetch(ref);
    await expect(store.update(ref, a.id, { status: "done" })).rejects.toEqual({ error: "no" });
    expect(store.steps("i1")?.[0].status).toBe("pending");
    await expect(store.reorder(ref, [b, a])).rejects.toEqual({ error: "no" });
    expect(store.steps("i1")?.map((s) => s.id)).toEqual([a.id, b.id]);
    expect(onSummary).toHaveBeenLastCalledWith("i1", expect.objectContaining({ done: 0, total: 2 }));
  });

  it("inserts a new step at its position", async () => {
    const [a, b] = [step(), step()];
    const added = step({ title: "middle" });
    const create = vi.fn().mockResolvedValue(added);
    const store = new StepsStore(api({ list: vi.fn().mockResolvedValue([a, b]), create }));
    await store.fetch(ref);
    await store.add(ref, { title: "middle" }, 1);
    expect(create).toHaveBeenCalledWith("acme", "p1", "i1", { title: "middle", position: 1 });
    expect(store.steps("i1")?.map((s) => s.title)).toEqual([a.title, "middle", b.title]);
  });
});
