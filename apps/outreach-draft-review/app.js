(function () {
  "use strict";

  const leads = Array.isArray(window.OUTREACH_DATA) ? window.OUTREACH_DATA : [];
  const initialLead = leads[0] || null;
  const state = {
    query: "",
    segment: "all",
    recipient: "all",
    country: "all",
    selectedEmail: initialLead?.email || "",
  };
  const paneWidthKey = "nexstudio-lead-pane-width-v1";

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
    workspace: document.querySelector(".workspace"),
    paneResizer: document.getElementById("paneResizer"),
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
    observation: document.getElementById("observation"),
    auditLabel: document.getElementById("auditLabel"),
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

  function leadDrafts(lead) {
    return Array.isArray(lead?.drafts) ? lead.drafts : [];
  }

  function render() {
    const filtered = filteredLeads();
    const lead = currentLead(filtered);
    if (lead && lead.email !== state.selectedEmail) {
      state.selectedEmail = lead.email;
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
    elements.companyName.textContent = lead.business_name;
    elements.companySegment.textContent = `${segmentLabel(lead.segment)} · ${recipientLabel(lead.recipient_type)}`;
    elements.contactLine.textContent =
      lead.recipient_type === "decision_maker"
        ? [lead.name, lead.title].filter(Boolean).join(" · ")
        : recipientLabel(lead.recipient_type);
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

  function clampPaneWidth(width) {
    const workspaceWidth = elements.workspace.getBoundingClientRect().width;
    const minimumLeadWidth = Math.max(320, workspaceWidth * 0.3);
    const minimumSignalWidth = 360;
    const resizerWidth = elements.paneResizer.offsetWidth;
    const maximumLeadWidth = Math.min(
      workspaceWidth * 0.75,
      workspaceWidth - minimumSignalWidth - resizerWidth,
    );
    return Math.max(
      minimumLeadWidth,
      Math.min(width, maximumLeadWidth),
    );
  }

  function setLeadPaneWidth(width, persist = false) {
    const nextWidth = clampPaneWidth(width);
    elements.workspace.style.setProperty("--lead-pane-width", `${nextWidth}px`);
    const percentage = Math.round(
      (nextWidth / elements.workspace.getBoundingClientRect().width) * 100,
    );
    elements.paneResizer.setAttribute("aria-valuenow", String(percentage));
    if (persist) {
      try {
        localStorage.setItem(paneWidthKey, String(nextWidth));
      } catch (_error) {
        // Resizing remains available for this session if storage is blocked.
      }
    }
  }

  function restoreLeadPaneWidth() {
    let savedWidth = 0;
    try {
      savedWidth = Number(localStorage.getItem(paneWidthKey) || 0);
    } catch (_error) {
      savedWidth = 0;
    }
    if (savedWidth > 0) setLeadPaneWidth(savedWidth);
  }

  function resizeFromPointer(event) {
    const bounds = elements.workspace.getBoundingClientRect();
    setLeadPaneWidth(event.clientX - bounds.left);
  }

  elements.paneResizer.addEventListener("pointerdown", (event) => {
    if (window.matchMedia("(max-width: 1100px)").matches) return;
    elements.paneResizer.setPointerCapture(event.pointerId);
    document.body.classList.add("is-resizing-panes");
    resizeFromPointer(event);
  });

  elements.paneResizer.addEventListener("pointermove", (event) => {
    if (!elements.paneResizer.hasPointerCapture(event.pointerId)) return;
    resizeFromPointer(event);
  });

  elements.paneResizer.addEventListener("pointerup", (event) => {
    if (!elements.paneResizer.hasPointerCapture(event.pointerId)) return;
    elements.paneResizer.releasePointerCapture(event.pointerId);
    document.body.classList.remove("is-resizing-panes");
    const currentWidth = parseFloat(
      getComputedStyle(elements.workspace).getPropertyValue("--lead-pane-width"),
    );
    setLeadPaneWidth(currentWidth, true);
  });

  elements.paneResizer.addEventListener("pointercancel", () => {
    document.body.classList.remove("is-resizing-panes");
  });

  elements.paneResizer.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentWidth = elements.leadList.closest(".lead-pane").getBoundingClientRect().width;
    if (event.key === "Home") setLeadPaneWidth(320, true);
    else if (event.key === "End") setLeadPaneWidth(Number.MAX_SAFE_INTEGER, true);
    else setLeadPaneWidth(currentWidth + (event.key === "ArrowLeft" ? -24 : 24), true);
  });

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

  restoreLeadPaneWidth();
  render();
})();
