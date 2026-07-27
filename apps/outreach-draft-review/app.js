(function () {
  "use strict";

  const leads = Array.isArray(window.OUTREACH_DATA) ? window.OUTREACH_DATA : [];
  const initialLead =
    leads.find((lead) => Array.isArray(lead.drafts) && lead.drafts.length) ||
    leads[0] ||
    null;
  const state = {
    query: "",
    segment: "all",
    recipient: "all",
    country: "all",
    selectedEmail: initialLead?.email || "",
    draftIndex: 0,
  };

  const trackingKey = "nexstudio-lead-tracking-v1";
  let tracking = {};
  try {
    tracking = JSON.parse(localStorage.getItem(trackingKey) || "{}");
  } catch (_error) {
    tracking = {};
  }

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
    leadTags: document.getElementById("leadTags"),
    copyEmail: document.getElementById("copyEmail"),
    copyWebsite: document.getElementById("copyWebsite"),
    copyClient: document.getElementById("copyClient"),
    copyCountry: document.getElementById("copyCountry"),
    emailValue: document.getElementById("emailValue"),
    websiteValue: document.getElementById("websiteValue"),
    clientValue: document.getElementById("clientValue"),
    countryValue: document.getElementById("countryValue"),
    mailDone: document.getElementById("mailDone"),
    followupDone: document.getElementById("followupDone"),
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
      filtered.find((lead) => leadDrafts(lead).length) ||
      filtered[0] ||
      null
    );
  }

  function leadDrafts(lead) {
    return Array.isArray(lead?.drafts) ? lead.drafts : [];
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
      leads.reduce((total, item) => total + leadDrafts(item).length, 0),
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
        icon.textContent = initials(lead.business_name);
        const image = document.createElement("img");
        image.alt = "";
        image.hidden = true;
        image.addEventListener("load", () => {
          image.hidden = false;
          icon.replaceChildren(image);
        });
        image.addEventListener("error", () => {
          image.remove();
          icon.textContent = initials(lead.business_name);
        });
        icon.appendChild(image);
        const iconUrl = faviconUrl(lead.website);
        if (iconUrl) image.src = iconUrl;

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

        const tags = document.createElement("span");
        tags.className = "lead-cell lead-tags";
        tags.textContent = segmentLabel(lead.segment);
        const country = document.createElement("span");
        country.className = "lead-cell";
        country.textContent = lead.country || "—";
        const location = document.createElement("span");
        location.className = "lead-cell";
        location.textContent = lead.city || "—";
        const email = document.createElement("span");
        email.className = "lead-cell lead-email";
        email.textContent = lead.email || "—";
        const offer = document.createElement("span");
        offer.className = "lead-cell lead-offer";
        offer.textContent = lead.price_range || lead.recommended_offer || "—";
        button.append(icon, copy, tags, country, location, email, offer);
        return button;
      }),
    );
  }

  function renderLead(lead) {
    const drafts = leadDrafts(lead);
    const draft = drafts[state.draftIndex] || drafts[0];
    const hasDraft = Boolean(draft);
    elements.companyName.textContent = lead.business_name;
    elements.companySegment.textContent = `${segmentLabel(lead.segment)} · ${recipientLabel(lead.recipient_type)}`;
    elements.contactLine.textContent =
      lead.recipient_type === "decision_maker"
        ? `${lead.name} · ${lead.title} · ${lead.email}`
        : `Business inbox · ${lead.email}`;
    renderCompanyIcon(lead);
    elements.websiteLink.href = lead.website;
    elements.offerName.textContent = lead.recommended_offer || "Growth build";
    elements.priceRange.textContent = lead.price_range || "—";
    elements.location.textContent =
      [lead.city, lead.country].filter(Boolean).join(", ") || "—";
    elements.leadTags.textContent = [segmentLabel(lead.segment), recipientLabel(lead.recipient_type)].join(" · ");
    elements.emailValue.value = lead.email || "—";
    elements.websiteValue.value = lead.website || "—";
    elements.clientValue.value = lead.business_name || "—";
    elements.countryValue.value = lead.country || "—";
    const leadTracking = tracking[lead.email] || {};
    elements.mailDone.checked = Boolean(leadTracking.mailDone);
    elements.followupDone.checked = Boolean(leadTracking.followupDone);
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
      ...drafts.map((item, index) => {
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
    elements.draftPosition.textContent = `Draft ${draft.number} of ${drafts.length} · ${draft.label}`;
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
    return leadDrafts(lead)[state.draftIndex] || null;
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
    const iconMarkup = {
      search: '<circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path>',
      inbox: '<path d="M4 4h16v12H4z"></path><path d="M4 12h4l2 3h4l2-3h4"></path>',
      "external-link": '<path d="M14 4h6v6"></path><path d="m20 4-9 9"></path><path d="M18 13v7H4V6h7"></path>',
      "scan-search": '<path d="M3 7V3h4"></path><path d="M17 3h4v4"></path><path d="M21 17v4h-4"></path><path d="M7 21H3v-4"></path><circle cx="11" cy="11" r="4"></circle><path d="m14 14 3 3"></path>',
      "shield-alert": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><path d="M12 8v4"></path><path d="M12 16h.01"></path>',
      copy: '<rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>',
    };
    document.querySelectorAll("i[data-lucide]").forEach((placeholder) => {
      const name = placeholder.dataset.lucide;
      const markup = iconMarkup[name];
      if (!markup) return;
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("fill", "none");
      svg.setAttribute("stroke", "currentColor");
      svg.setAttribute("stroke-width", "2");
      svg.setAttribute("stroke-linecap", "round");
      svg.setAttribute("stroke-linejoin", "round");
      svg.setAttribute("aria-hidden", "true");
      svg.dataset.icon = name;
      svg.innerHTML = markup;
      placeholder.replaceWith(svg);
    });
  }

  function renderCompanyIcon(lead) {
    const fallback = initials(lead.business_name) || "—";
    const iconUrl = faviconUrl(lead.website);
    elements.companyInitials.textContent = fallback;
    elements.companyInitials.hidden = false;
    elements.companyFavicon.hidden = true;
    elements.companyFavicon.onload = null;
    elements.companyFavicon.onerror = null;
    elements.companyFavicon.removeAttribute("src");
    if (!iconUrl) return;
    elements.companyFavicon.onload = () => {
      elements.companyFavicon.hidden = false;
      elements.companyInitials.hidden = true;
    };
    elements.companyFavicon.onerror = () => {
      elements.companyFavicon.hidden = true;
      elements.companyInitials.hidden = false;
    };
    elements.companyFavicon.src = iconUrl;
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

  function saveTracking(lead, field, value) {
    if (!lead?.email) return;
    tracking[lead.email] = { ...(tracking[lead.email] || {}), [field]: value };
    try {
      localStorage.setItem(trackingKey, JSON.stringify(tracking));
    } catch (_error) {
      // Tracking still remains available for this session if storage is blocked.
    }
  }

  elements.mailDone.addEventListener("change", (event) => {
    saveTracking(currentLead(filteredLeads()), "mailDone", event.target.checked);
  });

  elements.followupDone.addEventListener("change", (event) => {
    saveTracking(currentLead(filteredLeads()), "followupDone", event.target.checked);
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
