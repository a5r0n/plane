/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

type Props = { title: string; onClose: () => void; children: ReactNode };

/** A sheet from the bottom of the screen, for phone widths. */
export function BottomSheet({ title, onClose, children }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end md:hidden" role="dialog" aria-label={title}>
      <button type="button" aria-label="Close" className="flex-1 bg-black/40" onClick={onClose} />
      <div className="max-h-[80vh] overflow-y-auto rounded-t-lg border-t border-subtle bg-surface-1 p-4 pb-8">
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-layer-3" />
        <div className="mb-2 truncate text-14 font-medium text-primary">{title}</div>
        {children}
      </div>
    </div>
  );
}
