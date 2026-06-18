import { useState } from "react";

import ChatShellPreview from "./ChatShellPreview";
import GuardianControlsPreview from "./GuardianControlsPreview";
import LocalAiSettingsPreview from "./LocalAiSettingsPreview";
import ProviderSetupPreview from "./ProviderSetupPreview";
import RoadmapCard from "./RoadmapCard";
import RoundTablePreview from "./RoundTablePreview";
import ShellNavigation from "./ShellNavigation";
import StatusCard from "./StatusCard";
import WorkPagePreview from "./WorkPagePreview";
import { workstationRoadmapItems, workstationStatusItems, type WorkstationStatusItem } from "../workstation/workstationStatus";

type WorkstationShellProps = {
  statusItems?: WorkstationStatusItem[];
  statusSourceLabel?: string;
};

export default function WorkstationShell({
  statusItems = workstationStatusItems,
  statusSourceLabel = "Using local fallback status list."
}: WorkstationShellProps) {
  const [activeSectionId, setActiveSectionId] = useState("workstation-overview");

  return (
    <section className="workstation-shell" aria-label="Workstation shell status">
      <div className="workstation-shell-header">
        <h2>Workstation Shell</h2>
        <p>
          A read-only map of the current public shell surfaces. It shows what is available, what is previewed, and
          what remains guarded without enabling orchestration, chat runtime, model execution, or tool actions.
        </p>
      </div>

      <div className="workstation-layout">
        <ShellNavigation activeSectionId={activeSectionId} onSelectSection={setActiveSectionId} />

        <div className="workstation-content">
          <section className="section-panel" id="workstation-overview" aria-labelledby="workstation-overview-heading">
            <div className="section-panel-heading">
              <p className="eyebrow">Capability status</p>
              <h2 id="workstation-overview-heading">Workstation Overview</h2>
              <p>Current public shell status across the visible surfaces.</p>
              <p className="capabilities-source">{statusSourceLabel}</p>
            </div>

            <div className="status-grid">
              {statusItems.map((item) => (
                <StatusCard key={item.id} name={item.name} status={item.status} summary={item.summary} />
              ))}
            </div>
          </section>

          <ChatShellPreview />
          <RoundTablePreview />
          <WorkPagePreview />
          <LocalAiSettingsPreview />
          <ProviderSetupPreview />
          <GuardianControlsPreview />

          <div className="roadmap-grid">
            <RoadmapCard title="Planned Follow-up Work" items={workstationRoadmapItems} />
          </div>
        </div>
      </div>
    </section>
  );
}
