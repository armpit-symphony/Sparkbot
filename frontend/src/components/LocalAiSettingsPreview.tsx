const localAiSetupItems = [
  {
    name: "Local runtime setup",
    summary: "Ollama, LM Studio, llama.cpp, and compatible endpoint setup remain documentation-only in this baseline."
  },
  {
    name: "Model seats",
    summary: "Future seat labels and local model IDs are represented without editable fields or saved settings."
  },
  {
    name: "Readiness checks",
    summary: "Endpoint reachability checks are planned only; this public baseline does not call local or external providers."
  }
];

export default function LocalAiSettingsPreview() {
  return (
    <section
      className="local-ai-settings-preview section-panel"
      id="local-ai-settings"
      aria-labelledby="local-ai-settings-heading"
    >
      <div className="local-ai-settings-copy">
        <p className="eyebrow">Preview</p>
        <h2 id="local-ai-settings-heading">Local AI Settings Preview</h2>
        <p>
          A public-safe view of the local model setup route. It shows the intended installation and seat-readiness
          structure while keeping credentials, endpoint checks, model calls, and routing inactive.
        </p>
      </div>

      <div className="local-ai-settings-layout" aria-label="Read-only local AI settings preview">
        {localAiSetupItems.map((item) => (
          <article className="local-ai-settings-card" key={item.name}>
            <div className="local-ai-settings-card-top">
              <h3>{item.name}</h3>
              <span className="status-badge status-preview">Preview</span>
            </div>
            <p>{item.summary}</p>
          </article>
        ))}
      </div>

      <p className="local-ai-settings-note">
        This preview includes no credential fields, no save actions, no endpoint checks, no provider calls, and no model
        routing.
      </p>
    </section>
  );
}
