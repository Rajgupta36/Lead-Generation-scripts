(function () {
  "use strict";

  const leads = Array.isArray(window.OUTREACH_DATA) ? window.OUTREACH_DATA : [];
  const state = {
    query: "",
    segment: "all",
    recipient: "all",
    country: "all",
    selectedEmail: leads[0]?.email || "",
    draftIndex: 0,
  };

  const elements = {
    leadTotal: document.getElementById("leadTotal"),
    draftTotal: document.getElementById("draftTotal"),
    directTotal: document.getElementById("directTotal"),
    inboxTotal: document.getElementById("inboxTotal"),
    filteredCount: document.getElementById("filteredCount"),
    leadSearch: document.getElementById("leadSearch"),
    segmentFilter: document.getElementById("segmentFilter"),
    recipientFilter: document.getElementById("recipientFilter"),
    countryFilter: document.getElementById("countryFilter"),
    leadList: document.getElementById("leadList"),
    emptyState: document.getElementById("emptyState"),
    draftContent: document.getElementById("draftContent"),
    companyFavicon: document.getElementById("companyFavicon"),
    companyInitials: document.getElementById("companyInitials"),
    companySegment: document.getElementById("companySegment"),
    companyName: document.getElementById("companyName"),
    contactLine: document.getElementById("contactLine"),
    websiteLink: document.getElementById("websiteLink"),
    offerName: document.getElementById("offerName"),
    priceRange: document.getElementById("priceRange"),
    location: document.getElementById("location"),
    leadScore: document.getElementById("leadScore"),
    leadTags: document.getElementById("leadTags"),
    copyEmail: document.getElementById("copyEmail"),
    copyWebsite: document.getElementById("copyWebsite"),
    copyClient: document.getElementById("copyClient"),
    copyCountry: document.getElementById("copyCountry"),
    observation: document.getElementById("observation"),
    auditLabel: document.getElementById("auditLabel"),
    draftTabs: document.getElementById("draftTabs"),
    researchState: document.getElementById("researchState"),
    emailEditor: document.getElementById("emailEditor"),
    emailTo: document.getElementById("emailTo"),
    emailSubject: document.getElementById("emailSubject"),
    emailBody: document.getElementById("emailBody"),
    draftPosition: document.getElementById("draftPosition"),
    copySubject: document.getElementById("copySubject"),
    copyDraft: document.getElementById("copyDraft"),
    toast: document.getElementById("toast"),
  };

  function filteredLeads() {
    const query = state.query.trim().toLowerCase();
    return leads.filter((lead) => {
      const matchesSegment =
        state.segment === "all" || lead.segment === state.segment;
      const matchesRecipient =
        state.recipient === "all" || lead.recipient_type === state.recipient;
      const matchesCountry =
        state.country === "all" || lead.country === state.country;
      const haystack = [
        lead.business_name,
        lead.name,
        lead.email,
        lead.city,
        lead.country,
      ]
        .join(" ")
        .toLowerCase();
      return (
        matchesSegment &&
        matchesRecipient &&
        matchesCountry &&
        (!query || haystack.includes(query))
      );
    });
  }

  function currentLead(filtered) {
    return (
      filtered.find((lead) => lead.email === state.selectedEmail) ||
      filtered[0] ||
      null
    );
  }

  function render() {
    const filtered = filteredLeads();
    const lead = currentLead(filtered);
    if (lead && lead.email !== state.selectedEmail) {
      state.selectedEmail = lead.email;
      state.draftIndex = 0;
    }

    elements.leadTotal.textContent = String(leads.length);
    elements.draftTotal.textContent = String(
      leads.reduce((total, item) => total + item.drafts.length, 0),
    );
    elements.directTotal.textContent = String(
      leads.filter((lead) => lead.recipient_type === "decision_maker").length,
    );
    elements.inboxTotal.textContent = String(
      leads.filter((lead) => lead.recipient_type === "business_inbox").length,
    );
    elements.filteredCount.textContent = String(filtered.length);
    renderLeadList(filtered);

    const isEmpty = !lead;
    elements.emptyState.hidden = !isEmpty;
    elements.draftContent.hidden = isEmpty;
    if (!lead) {
      refreshIcons();
      return;
    }

    renderLead(lead);
    refreshIcons();
  }

  function renderLeadList(filtered) {
    elements.leadList.replaceChildren(
      ...filtered.map((lead) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `lead-row${lead.email === state.selectedEmail ? " active" : ""}`;
        button.dataset.email = lead.email;
        button.setAttribute("aria-label", `Open ${lead.business_name}`);

        const icon = document.createElement("span");
        icon.className = "lead-icon";
        const image = document.createElement("img");
        image.src = faviconUrl(lead.website);
        image.alt = "";
        image.addEventListener("error", () => {
          image.remove();
          icon.textContent = initials(lead.business_name);
        });
        icon.appendChild(image);

        const copy = document.createElement("span");
        copy.className = "lead-copy";
        const company = document.createElement("strong");
        company.textContent = lead.business_name;
        const person = document.createElement("span");
        person.textContent =
          lead.recipient_type === "decision_maker"
            ? `${lead.name} · ${segmentLabel(lead.segment)}`
            : `Business inbox · ${segmentLabel(lead.segment)}`;
        copy.append(company, person);

        const score = document.createElement("span");
        score.className = "lead-score";
        score.textContent = lead.lead_score || "—";
        button.append(icon, copy, score);
        return button;
      }),
    );
  }

  function renderLead(lead) {
    const draft = lead.drafts[state.draftIndex] || lead.drafts[0];
    const hasDraft = Boolean(draft);
    elements.companyName.textContent = lead.business_name;
    elements.companySegment.textContent = `${segmentLabel(lead.segment)} · ${recipientLabel(lead.recipient_type)}`;
    elements.contactLine.textContent =
      lead.recipient_type === "decision_maker"
        ? `${lead.name} · ${lead.title} · ${lead.email}`
        : `Business inbox · ${lead.email}`;
    elements.companyInitials.textContent = initials(lead.business_name);
    elements.companyFavicon.src = faviconUrl(lead.website);
    elements.companyFavicon.hidden = false;
    elements.companyInitials.hidden = true;
    elements.companyFavicon.onerror = () => {
      elements.companyFavicon.hidden = true;
      elements.companyInitials.hidden = false;
    };
    elements.websiteLink.href = lead.website;
    elements.offerName.textContent = lead.recommended_offer || "Growth build";
    elements.priceRange.textContent = lead.price_range || "—";
    elements.location.textContent =
      [lead.city, lead.country].filter(Boolean).join(", ") || "—";
    elements.leadScore.textContent = lead.lead_score || "—";
    elements.leadTags.textContent = [segmentLabel(lead.segment), recipientLabel(lead.recipient_type)].join(" · ");
    elements.copyEmail.textContent = lead.email || "—";
    elements.copyWebsite.textContent = lead.website || "—";
    elements.copyClient.textContent = lead.business_name || "—";
    elements.copyCountry.textContent = lead.country || "—";
    elements.copyEmail.disabled = !lead.email;
    elements.copyWebsite.disabled = !lead.website;
    elements.copyClient.disabled = !lead.business_name;
    elements.copyCountry.disabled = !lead.country;
    elements.observation.textContent =
      lead.specific_observation || "Website opportunity ready for review.";
    elements.auditLabel.textContent =
      lead.audit_status === "research_required"
        ? "Research-level signal"
        : "Website signal";

    elements.draftTabs.replaceChildren(
      ...lead.drafts.map((item, index) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = `draft-tab${index === state.draftIndex ? " active" : ""}`;
        tab.dataset.draftIndex = String(index);
        tab.role = "tab";
        tab.setAttribute("aria-selected", String(index === state.draftIndex));
        tab.textContent = `${index + 1}. ${item.label}`;
        return tab;
      }),
    );
    elements.draftTabs.hidden = !hasDraft;
    elements.researchState.hidden = hasDraft;
    elements.emailEditor.hidden = !hasDraft;
    if (!hasDraft) {
      return;
    }

    elements.emailTo.textContent = `${lead.name} <${lead.email}>`;
    elements.emailSubject.textContent = draft.subject;
    elements.emailBody.replaceChildren(
      ...draft.body.split("\n\n").map((paragraph) => {
        const node = document.createElement("p");
        node.textContent = paragraph;
        return node;
      }),
    );
    elements.draftPosition.textContent = `Draft ${draft.number} of ${lead.drafts.length} · ${draft.label}`;
  }

  async function copyText(value, successMessage) {
    try {
      await navigator.clipboard.writeText(value);
    } catch (_error) {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    showToast(successMessage);
  }

  function selectedDraft() {
    const lead = leads.find((item) => item.email === state.selectedEmail);
    return lead?.drafts[state.draftIndex] || null;
  }

  let toastTimer;
  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(
      () => elements.toast.classList.remove("show"),
      1500,
    );
  }

  function refreshIcons() {
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  function faviconUrl(website) {
    try {
      return `${new URL(website).origin}/favicon.ico`;
    } catch (_error) {
      return "";
    }
  }

  function initials(value) {
    return String(value || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase();
  }

  function segmentLabel(value) {
    return {
      agency_owner: "Agency",
      coach: "Coach",
      small_business: "Small business",
    }[value] || value;
  }

  function recipientLabel(value) {
    return value === "decision_maker" ? "Decision maker" : "Business inbox";
  }

  elements.leadSearch.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
  });

  elements.segmentFilter.addEventListener("change", (event) => {
    state.segment = event.target.value;
    render();
  });

  elements.recipientFilter.addEventListener("change", (event) => {
    state.recipient = event.target.value;
    render();
  });

  elements.countryFilter.addEventListener("change", (event) => {
    state.country = event.target.value;
    render();
  });

  elements.leadList.addEventListener("click", (event) => {
    const button = event.target.closest(".lead-row");
    if (!button) return;
    state.selectedEmail = button.dataset.email;
    state.draftIndex = 0;
    render();
  });

  elements.copyEmail.addEventListener("click", () => {
    const lead = currentLead(filteredLeads());
    if (lead?.email) copyText(lead.email, "Email copied");
  });

  elements.copyWebsite.addEventListener("click", () => {
    const lead = currentLead(filteredLeads());
    if (lead?.website) copyText(lead.website, "Website URL copied");
  });

  elements.copyClient.addEventListener("click", () => {
    const lead = currentLead(filteredLeads());
    if (lead?.business_name) copyText(lead.business_name, "Client name copied");
  });

  elements.copyCountry.addEventListener("click", () => {
    const lead = currentLead(filteredLeads());
    if (lead?.country) copyText(lead.country, "Country copied");
  });

  elements.draftTabs.addEventListener("click", (event) => {
    const button = event.target.closest(".draft-tab");
    if (!button) return;
    state.draftIndex = Number(button.dataset.draftIndex);
    render();
  });

  elements.copySubject.addEventListener("click", () => {
    const draft = selectedDraft();
    if (draft) copyText(draft.subject, "Subject copied");
  });

  elements.copyDraft.addEventListener("click", () => {
    const draft = selectedDraft();
    if (draft) {
      copyText(`Subject: ${draft.subject}\n\n${draft.body}`, "Draft copied");
    }
  });

  render();
})();
