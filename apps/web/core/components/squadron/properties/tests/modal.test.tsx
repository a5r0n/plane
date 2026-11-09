/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TPropertiesApi } from "../service";
import { PropertiesStore } from "../store";
import type { TProperty } from "../types";
import { choice, prop } from "./fixtures";

// Headless UI's Dialog measures with ResizeObserver, which jsdom lacks.
vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
);

const holder = vi.hoisted(() => ({ store: undefined as unknown }));
vi.mock("../use-properties", () => ({ useProperties: () => holder.store }));

const { PropertyModal } = await import("../settings/property-modal");
const { DeletePropertyModal } = await import("../settings/delete-property-modal");

afterEach(cleanup);

const setup = (defs: TProperty[], api: Partial<TPropertiesApi> = {}) => {
  const full = { list: vi.fn().mockResolvedValue(defs), ...api } as unknown as TPropertiesApi;
  const store = new PropertiesStore(full);
  store.byProject.p1 = defs;
  holder.store = store;
  return full;
};

const ref = { workspaceSlug: "acme", projectId: "p1" };

describe("PropertyModal", () => {
  it("fills the key from the name while creating", () => {
    setup([]);
    render(<PropertyModal isOpen onClose={vi.fn()} {...ref} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Story points" } });
    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("story_points");
  });

  it("stops following the name once the key is edited", () => {
    setup([]);
    render(<PropertyModal isOpen onClose={vi.fn()} {...ref} />);
    fireEvent.change(screen.getByLabelText("Key"), { target: { value: "pts" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Story points" } });
    expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe("pts");
  });

  it("locks key and type when editing", () => {
    const repo = choice({ name: "Repo", key: "repo" });
    setup([repo]);
    render(<PropertyModal isOpen onClose={vi.fn()} {...ref} property={repo} />);
    expect((screen.getByLabelText("Key") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Type") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Keys never change; PQL and the API use them")).toBeTruthy();
  });

  it("sends only the changed options, with ids kept, when an option is disabled", async () => {
    const repo = choice({ name: "Repo", key: "repo" });
    const update = vi.fn().mockImplementation((_s, _p, _id, data) => Promise.resolve({ ...repo, ...data }));
    setup([repo], { update });
    const onClose = vi.fn();
    render(<PropertyModal isOpen onClose={onClose} {...ref} property={repo} />);
    fireEvent.click(screen.getByRole("button", { name: "Disable Beta" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(update).toHaveBeenCalledWith("acme", "p1", repo.id, {
      options: [
        { id: "a", label: "Alpha", disabled: false },
        { id: "b", label: "Beta", disabled: true },
      ],
    });
  });

  it("adds new options without an id", async () => {
    const repo = choice({ name: "Repo", key: "repo" });
    const update = vi.fn().mockImplementation((_s, _p, _id, data) => Promise.resolve({ ...repo, ...data }));
    setup([repo], { update });
    render(<PropertyModal isOpen onClose={vi.fn()} {...ref} property={repo} />);
    fireEvent.click(screen.getByRole("button", { name: "Add option" }));
    fireEvent.change(screen.getByLabelText("Option 3"), { target: { value: "plane" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    const options = update.mock.calls[0][3].options;
    expect(options[2]).toEqual({ label: "plane", disabled: false });
  });

  it("keeps the modal open with the server's reason on 400", async () => {
    const create = vi.fn().mockRejectedValue({ key: ["key 'repo' is already used in this project"] });
    setup([], { create });
    const onClose = vi.fn();
    render(<PropertyModal isOpen onClose={onClose} {...ref} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Repo" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("key 'repo' is already used in this project")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows a refused option removal under the options list", async () => {
    const repo = choice({ name: "Repo", key: "repo" });
    const update = vi.fn().mockRejectedValue({ options: ["2 items hold 'Beta'; disable it instead"] });
    setup([repo], { update });
    render(<PropertyModal isOpen onClose={vi.fn()} {...ref} property={repo} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Beta" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const message = await screen.findByText("2 items hold 'Beta'; disable it instead");
    expect(message.closest("[data-options]")).toBeTruthy();
  });
});

describe("DeletePropertyModal", () => {
  it("confirms and removes the definition", async () => {
    const repo = prop({ name: "Repo", key: "repo" });
    const remove = vi.fn().mockResolvedValue(undefined);
    setup([repo], { remove });
    const onClose = vi.fn();
    render(<DeletePropertyModal isOpen onClose={onClose} {...ref} property={repo} />);
    expect(screen.getByText("Delete Repo?")).toBeTruthy();
    expect(screen.getByText(/Values stay stored but stop showing anywhere/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("acme", "p1", repo.id));
    expect(onClose).toHaveBeenCalled();
  });
});
