/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StepChip } from "../step-chip";
import { FinishForm } from "../track/finish-form";
import { Track } from "../track/track";
import type { TStepHandlers } from "../track/types";
import { YourTurnBar } from "../your-turn-bar";
import { FUTURE, step } from "./fixtures";

afterEach(cleanup);

const handlers = (): TStepHandlers => ({
  add: vi.fn().mockResolvedValue(undefined),
  update: vi.fn().mockResolvedValue(undefined),
  remove: vi.fn().mockResolvedValue(undefined),
  reorder: vi.fn().mockResolvedValue(undefined),
});

const summary = (over = {}) => ({
  done: 1,
  total: 3,
  current: { id: "c", title: "review", status: "pending" as const, not_before: null, actor: "me", ...over },
});

const actorOf = () => undefined;

describe("FinishForm", () => {
  it("won't mark failed without a note", async () => {
    const onSubmit = vi.fn();
    render(<FinishForm outcome="failed" onSubmit={onSubmit} onCancel={vi.fn()} />);
    const submit = screen.getByRole("button", { name: "Mark failed" });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText("Note"), "   ");
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText("Note"), "tests red");
    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith("tests red");
  });

  it("marks done without a note", async () => {
    const onSubmit = vi.fn();
    render(<FinishForm outcome="done" onSubmit={onSubmit} onCancel={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Mark done" }));
    expect(onSubmit).toHaveBeenCalledWith("");
  });
});

describe("StepChip", () => {
  it("reads n/m and the current title, amber on the viewer's turn", () => {
    const { container } = render(<StepChip summary={summary()} viewerId="me" />);
    expect(container.textContent).toContain("1/3");
    expect(container.textContent).toContain("review");
    expect(container.firstElementChild?.getAttribute("data-tone")).toBe("turn");
  });

  it("is red when failed, grey while waiting, neutral for someone else", () => {
    const tone = (over: object, viewer = "me") =>
      render(<StepChip summary={summary(over)} viewerId={viewer} />).container.firstElementChild?.getAttribute(
        "data-tone"
      );
    expect(tone({ status: "failed" })).toBe("failed");
    expect(tone({ not_before: FUTURE })).toBe("waiting");
    expect(tone({}, "you")).toBe("neutral");
  });

  it("renders nothing without steps", () => {
    expect(render(<StepChip summary={null} />).container.innerHTML).toBe("");
  });
});

describe("YourTurnBar", () => {
  it("finishes through the sheet, and a failed step offers Retry", async () => {
    const onFinish = vi.fn();
    const { rerender } = render(<YourTurnBar step={step({ title: "deploy" })} onFinish={onFinish} onRetry={vi.fn()} />);
    expect(screen.getByText("Your turn: deploy")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Failed" }));
    expect((screen.getByRole("button", { name: "Mark failed" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText("Note"), "500s");
    await userEvent.click(screen.getByRole("button", { name: "Mark failed" }));
    expect(onFinish).toHaveBeenCalledWith("failed", "500s");

    const onRetry = vi.fn();
    rerender(<YourTurnBar step={step({ title: "deploy", status: "failed" })} onFinish={onFinish} onRetry={onRetry} />);
    expect(screen.getByText("Failed: deploy")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("Track", () => {
  it("folds done steps and opens the current one as a card", () => {
    const steps = [
      step({ status: "done" }),
      step({ status: "skipped" }),
      step({ title: "now" }),
      step({ title: "later" }),
    ];
    render(<Track steps={steps} actorOf={actorOf} handlers={handlers()} narrow />);
    expect(screen.getByText("✓ 2 done")).toBeTruthy();
    expect(document.getElementById(`step-card-${steps[2].id}`)).not.toBeNull();
    expect(document.getElementById(`step-card-${steps[3].id}`)).toBeNull();
  });

  it("moves a step down from the phone sheet", async () => {
    const steps = [step({ title: "a" }), step({ title: "b" }), step({ title: "c" })];
    const h = handlers();
    render(<Track steps={steps} actorOf={actorOf} handlers={h} narrow />);
    await userEvent.click(screen.getAllByRole("button", { name: "Step actions" })[0]);
    await userEvent.click(screen.getByRole("button", { name: "Move down" }));
    expect(h.reorder).toHaveBeenCalledWith([steps[1], steps[0], steps[2]]);
  });

  it("marks later rows held behind a failed step", () => {
    const steps = [step({ status: "failed", note: "boom" }), step()];
    render(<Track steps={steps} actorOf={actorOf} handlers={handlers()} narrow />);
    expect(screen.getByText("Failed: boom")).toBeTruthy();
    expect(screen.getByText(/held by failed step/)).toBeTruthy();
  });

  it("Start now clears not_before", async () => {
    const waiting = step({ not_before: FUTURE });
    const h = handlers();
    render(<Track steps={[waiting]} actorOf={actorOf} handlers={h} narrow />);
    await userEvent.click(screen.getByRole("button", { name: "Start now" }));
    expect(h.update).toHaveBeenCalledWith(waiting.id, { not_before: null });
  });
});
