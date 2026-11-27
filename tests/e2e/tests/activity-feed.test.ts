/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { beforeAll, describe, expect, inject, it } from "vitest";
import { ApiClient } from "../src/plane";

const stack = inject("stack");
const api = new ApiClient(stack.apiKey, stack.workspaceSlug);
const items = `projects/${stack.projectId}/work-items/`;

type Row = { id: string; field: string | null; issue: string | null; issue_identifier: string | null };
type Feed = { reader: string; batch: string | null; more: boolean; results: Row[] };

const feed = (query: Record<string, string | number>) =>
  api.call<Feed>(
    "GET",
    `activities/?${new URLSearchParams(Object.entries(query).map(([k, v]): [string, string] => [k, String(v)]))}`
  );

// Ack everything the reader has now, so later calls see only new rows; returns what it acked.
async function drain(first: Feed) {
  const seen = [...first.results];
  let page = first;
  while (page.batch) {
    // oxlint-disable-next-line no-await-in-loop -- each call acks the batch before it
    page = await feed({ reader: first.reader, ack: page.batch });
    seen.push(...page.results);
  }
  return seen;
}

async function timed<T>(call: Promise<T>) {
  const started = Date.now();
  const value = await call;
  return { value, seconds: (Date.now() - started) / 1000 };
}

describe("workspace activity feed", () => {
  let itemId: string;
  let reader: string;

  beforeAll(async () => {
    itemId = (await api.call<{ id: string }>("POST", items, { name: "Feed E2E" })).id;
    await api.call("POST", `${items}${itemId}/steps/`, { title: "build" });
  });

  it("gives a new reader the recent rows with the item's identifier", async () => {
    const first = await feed({ reader: "new" });
    reader = first.reader;
    const step = (await drain(first)).find((row) => row.issue === itemId && row.field === "step");
    expect(step?.issue_identifier).toMatch(/^[A-Z]+-\d+$/);
  });

  it("returns empty after the wait once everything is acked", async () => {
    // other files write meanwhile: watch a field nobody writes
    const { value, seconds } = await timed(feed({ reader, wait: 2, field: "none" }));
    expect(value.results).toEqual([]);
    expect(seconds).toBeGreaterThanOrEqual(1.8);
  });

  it("wakes a held request when a row lands", async () => {
    // other files' step rows may wake it first: keep holding until ours comes
    const ours = (page: Feed) => page.results.some((row) => row.issue === itemId && row.field === "step");
    let page = feed({ reader, wait: 15, field: "step" });
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const posted = Date.now();
    await api.call("POST", `${items}${itemId}/steps/`, { title: "deploy" });
    let got = await page;
    while (!ours(got) && Date.now() - posted < 15_000) {
      page = feed({ reader, ack: got.batch ?? "", wait: 15, field: "step" });
      // oxlint-disable-next-line no-await-in-loop -- each call acks the batch before it
      got = await page;
    }
    expect(ours(got)).toBe(true);
    expect((Date.now() - posted) / 1000).toBeLessThan(5);
    await drain({ ...got, reader });
  });

  it("keeps serving other requests while more requests are held than there are workers", async () => {
    const readers = await Promise.all([0, 1, 2].map(() => feed({ reader: "new" })));
    await Promise.all(readers.map(drain));
    const held = readers.map((page) => timed(feed({ reader: page.reader, wait: 6, field: "none" })));
    await new Promise((resolve) => setTimeout(resolve, 500));
    const plain = await timed(api.call("GET", `${items}${itemId}/`));
    expect(plain.seconds).toBeLessThan(2);
    for (const { value, seconds } of await Promise.all(held)) {
      expect(value.results).toEqual([]);
      expect(seconds).toBeGreaterThanOrEqual(5.5);
    }
  });
});
