(() => {
  const workflows = [
    ["Discovery", "generate:maps", "Google Maps / local businesses", "Find local businesses with map ratings and contact signals."],
    ["Discovery", "generate:apollo", "Apollo-enriched dorks", "Discover prospects and enrich their organizations."],
    ["Discovery", "generate:directories", "Niche directory seeds", "Import and qualify directory-based seed lists."],
    ["Discovery", "generate:opportunities", "Website opportunities", "Find visible website-improvement signals."],
    ["Discovery", "generate:lookalikes", "Lookalike leads", "Generate leads matching your ideal customer profile."],
    ["Discovery", "generate:x-founders", "X Premium founders", "Prepare founder candidates and verification batches."],
    ["Campaigns", "generate:americas", "Americas review campaign", "Generate review-only North and South America prospects."],
    ["Campaigns", "generate:americas-email", "Americas email campaign", "Generate Americas leads with websites and matched business emails."],
    ["Continuous loop", "generate:business-leads", "Business leads", "Run the next rotating business discovery cycle."],
    ["Continuous loop", "generate:coach-leads", "Coach leads", "Run the next rotating coach discovery cycle."],
    ["Continuous loop", "generate:agency-partner-leads", "Agency partner leads", "Find partner agencies without web, SEO, or development overlap."],
    ["Continuous loop", "generate:lead-workflows", "All continuous workflows", "Run businesses, coaches, and agency partners together."],
    ["Enrichment", "enrich:decision-makers", "Decision-maker enrichment", "Find public founder, owner, or CEO evidence."],
    ["Enrichment", "review:decision-makers", "Apply decision-maker review", "Apply reviewed corrections and build the sendable queue."],
    ["Meeting preparation", "generate:audits", "Personalized audits", "Create evidence-backed website audit reports."],
    ["Meeting preparation", "generate:meetings", "Meeting queue", "Qualify leads, match offers, and prepare meeting outreach."],
    ["Meeting preparation", "generate:nexstudio", "NexStudio pipeline", "Run the complete discovery-to-meeting pipeline."],
    ["Review", "generate:drafts", "Refresh outreach drafts", "Generate five reviewable meeting emails per approved lead."],
  ];

  const root = document.getElementById("workflowGroups");
  const toast = document.getElementById("toast");
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
  const groups = workflows.reduce((result, workflow) => ((result[workflow[0]] ||= []).push(workflow), result), {});

  root.innerHTML = Object.entries(groups).map(([group, items]) => `
    <section class="workflow-group">
      <div class="group-title"><p class="eyebrow">${escapeHtml(group)}</p><span>${items.length} workflows</span></div>
      <div class="workflow-grid">${items.map(([, command, label, description]) => `
        <article class="workflow-card">
          <div class="card-mark">${escapeHtml(label.slice(0, 1))}</div>
          <h2>${escapeHtml(label)}</h2>
          <p>${escapeHtml(description)}</p>
          <div class="command"><code>pnpm ${escapeHtml(command)}</code><button type="button" data-command="pnpm ${escapeHtml(command)}">Copy</button></div>
        </article>`).join("")}</div>
    </section>`).join("");

  let timer;
  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(timer);
    timer = window.setTimeout(() => toast.classList.remove("visible"), 1600);
  }

  root.querySelectorAll("button[data-command]").forEach((button) => button.addEventListener("click", async () => {
    const command = button.dataset.command;
    try { await navigator.clipboard.writeText(command); } catch (_error) {
      const input = document.createElement("textarea"); input.value = command; document.body.appendChild(input); input.select(); document.execCommand("copy"); input.remove();
    }
    showToast("Command copied");
  }));
})();
