const workPreviewItems = [
  {
    name: "Program queue",
    summary: "Draft work program structure for future worker assignments, shown without scheduling or execution."
  },
  {
    name: "Workspace files",
    summary: "SOP and work-file slots are visible as a planning surface only; no file reads, writes, or uploads occur."
  },
  {
    name: "Remote index",
    summary: "Network-drive search is represented as a planned capability, with no connector calls or external access."
  }
];

export default function WorkPagePreview() {
  return (
    <section className="work-page-preview section-panel" id="work-page" aria-labelledby="work-page-heading">
      <div className="work-page-copy">
        <p className="eyebrow">Preview</p>
        <h2 id="work-page-heading">Work Page Preview</h2>
        <p>
          A public-safe preview of the work surface from the shell track: program intake, workspace files, and staged
          search concepts are visible without activating local file APIs, connector calls, model work, or mutations.
        </p>
      </div>

      <div className="work-preview-layout" aria-label="Read-only work page preview">
        {workPreviewItems.map((item) => (
          <article className="work-preview-card" key={item.name}>
            <div className="work-preview-card-top">
              <h3>{item.name}</h3>
              <span className="status-badge status-preview">Preview</span>
            </div>
            <p>{item.summary}</p>
          </article>
        ))}
      </div>

      <p className="work-page-note">
        This preview includes no upload controls, no document editor, no network search action, and no filesystem write
        behavior.
      </p>
    </section>
  );
}
