/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useTranslation } from "@plane/i18n";
import { EpicIcon } from "@plane/propel/icons";
import { useIsEpic } from "./use-is-epic";

/** "Epic" mark beside the identifier on an epic's detail page. */
export const EpicBadge = observer(function EpicBadge({ issueId }: { issueId: string }) {
  const { t } = useTranslation();
  const isEpic = useIsEpic(issueId);
  if (!isEpic) return null;
  return (
    <span className="flex items-center gap-1 text-caption-md-medium text-secondary">
      <EpicIcon className="size-4 flex-shrink-0" />
      {t("common.epic")}
    </span>
  );
});
