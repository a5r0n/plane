/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { EIssueLayoutTypes, EIssuesStoreType } from "@plane/types";
import { IssuePeekOverview } from "@/components/issues/peek-overview";
import { BaseGanttRoot } from "@/components/issues/issue-layouts/gantt";
import { CalendarLayout } from "@/components/issues/issue-layouts/calendar/roots/project-root";
import { KanBanLayout } from "@/components/issues/issue-layouts/kanban/roots/project-root";
import { ListLayout } from "@/components/issues/issue-layouts/list/roots/project-root";
import { ProjectSpreadsheetLayout } from "@/components/issues/issue-layouts/spreadsheet/roots/project-root";
import { useIssues } from "@/hooks/store/use-issues";
import { IssuesStoreContext } from "@/hooks/use-issue-layout-store";

function EpicLayout({ layout }: { layout?: EIssueLayoutTypes }) {
  switch (layout) {
    case EIssueLayoutTypes.LIST:
      return <ListLayout />;
    case EIssueLayoutTypes.KANBAN:
      return <KanBanLayout />;
    case EIssueLayoutTypes.CALENDAR:
      return <CalendarLayout />;
    case EIssueLayoutTypes.GANTT:
      return <BaseGanttRoot />;
    case EIssueLayoutTypes.SPREADSHEET:
      return <ProjectSpreadsheetLayout />;
    default:
      return null;
  }
}

export const EpicsLayoutRoot = observer(function EpicsLayoutRoot() {
  const { workspaceSlug, projectId } = useParams();
  const { issuesFilter } = useIssues(EIssuesStoreType.EPIC);
  const ws = workspaceSlug?.toString();
  const pid = projectId?.toString();

  useSWR(
    ws && pid ? `PROJECT_EPICS_${ws}_${pid}` : null,
    async () => ws && pid && (await issuesFilter?.fetchFilters(ws, pid)),
    { revalidateIfStale: false, revalidateOnFocus: false }
  );

  const filters = pid ? issuesFilter?.getIssueFilters(pid) : undefined;
  if (!ws || !pid || !filters) return <></>;
  return (
    <IssuesStoreContext.Provider value={EIssuesStoreType.EPIC}>
      <div className="relative h-full w-full overflow-auto bg-surface-1">
        <EpicLayout layout={filters.displayFilters?.layout} />
      </div>
      <IssuePeekOverview />
    </IssuesStoreContext.Provider>
  );
});
