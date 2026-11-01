/**
 * Kazama Protocol - Frontend Application Controller
 * Handles user interactions, cinematic step transitions, 3D cross-linking,
 * and multi-decision evaluation ledger.
 */

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize 3D Scene
    const scene = new NeuralSpaceScene("canvas-container");

    // State
    const state = {
        urls: [],
        files: [],
        lastAnalysis: null,
        activeNode: null,
        decisionCount: 0,
    };

    // DOM Elements
    const intakeView = document.getElementById("intake-view");
    const workspaceView = document.getElementById("workspace-view");
    const centerPanel = document.getElementById("center-panel");
    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingText = document.getElementById("loading-step-text");

    const queryInput = document.getElementById("query-input");
    const urlInput = document.getElementById("url-input");
    const addUrlBtn = document.getElementById("add-url-btn");
    const urlChips = document.getElementById("url-chips");
    const fileUpload = document.getElementById("file-upload");
    const fileChips = document.getElementById("file-chips");
    const mockModeToggle = document.getElementById("mock-mode-toggle");
    const exploreBtn = document.getElementById("explore-btn");
    const resetBtn = document.getElementById("reset-btn");
    const scenarioPill = document.getElementById("scenario-pill");

    // Workspace Elements
    const activeQueryText = document.getElementById("active-query-text");
    const activeAttachments = document.getElementById("active-attachments");
    const sourcesCountBadge = document.getElementById("sources-count-badge");
    const sourcesList = document.getElementById("sources-list");
    const summaryText = document.getElementById("summary-text");
    const factsContainer = document.getElementById("facts-container");
    const conflictsContainer = document.getElementById("conflicts-container");
    const missingContainer = document.getElementById("missing-container");

    // Decision Elements
    const decisionInput = document.getElementById("decision-input");
    const submitDecisionBtn = document.getElementById("submit-decision-btn");
    const decisionHistoryContainer = document.getElementById("decision-history-container");

    // Floating Card
    const floatingCard = document.getElementById("floating-node-card");
    const closeFloatingCard = document.getElementById("close-floating-card");
    const floatingSourceId = document.getElementById("floating-source-id");
    const floatingTrustBadge = document.getElementById("floating-trust-badge");
    const floatingTitle = document.getElementById("floating-title");
    const floatingExcerpt = document.getElementById("floating-excerpt");
    const floatingLink = document.getElementById("floating-link");

    // Status & Notification Elements
    const backendStatusPill = document.getElementById("backend-status-pill");
    const offlineBanner = document.getElementById("offline-banner");
    const toastContainer = document.getElementById("toast-container");

    // About / Made By Modal Elements
    const brandTrigger = document.getElementById("brand-trigger");
    const aboutModal = document.getElementById("about-modal");
    const closeAboutModal = document.getElementById("close-about-modal");

    if (brandTrigger && aboutModal) {
        brandTrigger.addEventListener("click", () => {
            aboutModal.classList.remove("hidden");
        });
    }

    if (closeAboutModal && aboutModal) {
        closeAboutModal.addEventListener("click", () => {
            aboutModal.classList.add("hidden");
        });
    }

    if (aboutModal) {
        aboutModal.addEventListener("click", (e) => {
            if (e.target === aboutModal) {
                aboutModal.classList.add("hidden");
            }
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && !aboutModal.classList.contains("hidden")) {
                aboutModal.classList.add("hidden");
            }
        });
    }

    // --- On-Site Toast Notification System (Replaces raw alerts) ---
    function showToast(title, message, type = "error", duration = 6000) {
        if (!toastContainer) return;
        const toast = document.createElement("div");
        toast.className = `site-toast ${type}`;
        
        let icon = "⚠️";
        if (type === "success") icon = "✅";
        else if (type === "error") icon = "❌";

        toast.innerHTML = `
            <div class="toast-header">
                <span class="toast-title">${icon} ${title}</span>
                <span class="toast-close">×</span>
            </div>
            <div class="toast-body">${message}</div>
        `;

        toast.querySelector(".toast-close").addEventListener("click", () => {
            toast.remove();
        });

        toastContainer.appendChild(toast);

        setTimeout(() => {
            if (toast.parentElement) {
                toast.style.opacity = "0";
                toast.style.transform = "translateY(10px)";
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    }

    // --- Backend Health Check on Initial Launch ---
    async function checkBackendHealth() {
        if (!backendStatusPill) return;
        try {
            const res = await fetch("/api/health", { cache: "no-store" });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            
            backendStatusPill.className = "status-pill online";
            const modelLabel = data.llm_model ? data.llm_model.replace("gemini-", "") : "LIVE";
            backendStatusPill.innerHTML = `<span class="status-dot"></span><span class="status-text">ONLINE • ${modelLabel.toUpperCase()}</span>`;
            if (offlineBanner) offlineBanner.classList.add("hidden");
        } catch (err) {
            console.warn("Backend health check failed:", err);
            backendStatusPill.className = "status-pill offline";
            backendStatusPill.innerHTML = `<span class="status-dot"></span><span class="status-text">OFFLINE</span>`;

            if (offlineBanner) {
                offlineBanner.classList.remove("hidden");
                offlineBanner.innerHTML = `
                    <span>⚠️ <strong>FastAPI Backend Offline</strong>: Unable to reach <code>/api/health</code>. Live crawls and Gemini synthesis require the backend server.</span>
                    <button id="banner-mock-btn" class="pill-btn" style="padding: 2px 10px; font-size: 0.65rem; background: rgba(255,255,255,0.15); color: #fff;">Enable Mock Mode</button>
                    <button id="banner-retry-btn" class="pill-btn secondary" style="padding: 2px 10px; font-size: 0.65rem;">Retry</button>
                `;
                document.getElementById("banner-mock-btn")?.addEventListener("click", () => {
                    mockModeToggle.checked = true;
                    showToast("Offline Mock Mode Enabled", "Queries will use simulated local ground truth.", "warning", 4000);
                    offlineBanner.classList.add("hidden");
                });
                document.getElementById("banner-retry-btn")?.addEventListener("click", () => {
                    checkBackendHealth();
                });
            }

            showToast("Backend Server Offline", "Unable to connect to FastAPI gateway on port 8000. Launch backend or enable Mock Mode.", "warning", 7000);
        }
    }

    // Run health check on initial load
    checkBackendHealth();

    // --- URL Handling ---
    function addUrl() {
        const val = urlInput.value.trim();
        if (!val) return;
        try {
            new URL(val);
        } catch (_) {
            showToast("Invalid URL", "Please enter a valid URL (including http:// or https://)", "warning");
            return;
        }
        if (!state.urls.includes(val)) {
            state.urls.push(val);
            renderUrlChips();
        }
        urlInput.value = "";
    }

    addUrlBtn.addEventListener("click", addUrl);
    urlInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            addUrl();
        }
    });

    function renderUrlChips() {
        urlChips.innerHTML = "";
        state.urls.forEach((u, idx) => {
            const chip = document.createElement("div");
            chip.className = "chip";
            chip.innerHTML = `<span>🔗 ${new URL(u).hostname}</span><span class="chip-remove" data-idx="${idx}">×</span>`;
            urlChips.appendChild(chip);
        });
        urlChips.querySelectorAll(".chip-remove").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const idx = parseInt(e.target.getAttribute("data-idx"));
                state.urls.splice(idx, 1);
                renderUrlChips();
            });
        });
    }

    // --- File Handling ---
    fileUpload.addEventListener("change", (e) => {
        const files = Array.from(e.target.files);
        files.forEach(file => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = reader.result.split(",")[1];
                state.files.push({
                    filename: file.name,
                    content_base64: base64,
                    mime_type: file.type || "text/plain",
                });
                renderFileChips();
            };
            reader.readAsDataURL(file);
        });
    });

    function renderFileChips() {
        fileChips.innerHTML = "";
        state.files.forEach((f, idx) => {
            const chip = document.createElement("div");
            chip.className = "chip";
            chip.innerHTML = `<span>📄 ${f.filename}</span><span class="chip-remove" data-idx="${idx}">×</span>`;
            fileChips.appendChild(chip);
        });
        fileChips.querySelectorAll(".chip-remove").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const idx = parseInt(e.target.getAttribute("data-idx"));
                state.files.splice(idx, 1);
                renderFileChips();
            });
        });
    }

    // --- Scenario Presets ---
    scenarioPill.addEventListener("click", () => {
        queryInput.value = "What are the eligibility criteria and deadlines for NMES scholarship?";
        mockModeToggle.checked = true;
        triggerAnalysis();
    });

    // --- Reset Flow ---
    resetBtn.addEventListener("click", () => {
        workspaceView.classList.add("hidden");
        intakeView.classList.remove("hidden");
        resetBtn.style.display = "none";
        decisionHistoryContainer.innerHTML = "";
        floatingCard.classList.add("hidden");
        state.lastAnalysis = null;
        state.decisionCount = 0;
        scene.setPaneMode(false);
        scene.populateSources([]);
        scene.focusOverview();
    });

    // --- Explore & Analyze (Cinematic Step-by-Step Transition) ---
    exploreBtn.addEventListener("click", triggerAnalysis);

    async function triggerAnalysis() {
        const query = queryInput.value.trim();
        if (query.length < 3) {
            showToast("Query Required", "Please enter a research query or goal (at least 3 characters).", "warning");
            return;
        }

        exploreBtn.disabled = true;
        exploreBtn.style.opacity = "0.6";
        scene.setSynthesizing(true);

        // 1. Immediately transition from centered intake view to 3-pane mode
        intakeView.classList.add("hidden");
        workspaceView.classList.remove("hidden");
        resetBtn.style.display = "block";
        scene.setPaneMode(true);
        scene.focusOverview();

        // 2. Set up Left Panel immediately with query & searching skeleton
        activeQueryText.textContent = query;
        renderActiveAttachments();
        sourcesCountBadge.textContent = "...";
        sourcesList.innerHTML = `
            <div style="padding: 24px 12px; text-align: center; color: var(--text-muted); font-size: 0.74rem;">
                <div class="loading-spinner" style="width: 20px; height: 20px; margin: 0 auto 10px;"></div>
                Crawling ground truth nodes & weighting sources...
            </div>
        `;

        // 3. Keep Center Panel HIDDEN while search and 3D branch spawning occur
        centerPanel.classList.add("hidden");
        centerPanel.style.opacity = "0";
        decisionHistoryContainer.innerHTML = "";
        state.decisionCount = 0;

        // Subtle ambient status banner
        loadingOverlay.classList.remove("hidden");
        loadingText.textContent = "Ingesting Ground Truth Sources...";

        const payload = {
            query: query,
            decision: null,
            urls: state.urls,
            files: state.files,
            options: {
                mock_mode: mockModeToggle.checked,
                use_search: true,
                include_debug: true,
            }
        };

        try {
            const res = await fetch("/api/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                const msg = errData?.error?.message || errData?.detail || `Server returned HTTP ${res.status}`;
                throw new Error(msg);
            }

            const data = await res.json();
            state.lastAnalysis = data;

            // Sources are here! Ingested sources immediately display in left panel
            renderSourcesPanel(data.sources);
            loadingText.textContent = "Synthesizing Evidence & Spawning Constellation...";

            // 4. Make branches spawn outward from nucleus, then spawn nodes & labels
            scene.populateSources(data.sources, () => {
                // 5. AFTER animation completes AND LLM response is ready -> Overlay center pane!
                loadingOverlay.classList.add("hidden");
                overlayCenterPane(data);
            });

        } catch (err) {
            console.error(err);
            loadingOverlay.classList.add("hidden");
            showToast("Pipeline Analysis Failed", err.message, "error", 8000);
            // Return to intake view on failure
            workspaceView.classList.add("hidden");
            intakeView.classList.remove("hidden");
            scene.setPaneMode(false);
            scene.focusOverview();
        } finally {
            scene.setSynthesizing(false);
            exploreBtn.disabled = false;
            exploreBtn.style.opacity = "1";
        }
    }

    // --- Overlay Center Pane ---
    function overlayCenterPane(data) {
        renderDossier(data);
        centerPanel.classList.remove("hidden");
        if (typeof gsap !== 'undefined') {
            gsap.fromTo(centerPanel, 
                { opacity: 0, y: 22 },
                { opacity: 1, y: 0, duration: 0.65, ease: "power2.out" }
            );
        } else {
            centerPanel.style.opacity = "1";
        }
    }

    function renderActiveAttachments() {
        activeAttachments.innerHTML = "";
        if (state.urls.length > 0 || state.files.length > 0) {
            const list = document.createElement("div");
            list.className = "chips-container";
            state.urls.forEach(u => {
                const c = document.createElement("span");
                c.className = "chip";
                c.textContent = `🔗 ${new URL(u).hostname}`;
                list.appendChild(c);
            });
            state.files.forEach(f => {
                const c = document.createElement("span");
                c.className = "chip";
                c.textContent = `📄 ${f.filename}`;
                list.appendChild(c);
            });
            activeAttachments.appendChild(list);
        }
    }

    function renderSourcesPanel(sources) {
        sourcesCountBadge.textContent = sources.length;
        sourcesList.innerHTML = "";
        sources.forEach(src => {
            const card = document.createElement("div");
            card.className = "source-item-card";
            card.id = `source-card-${src.source_id}`;

            const trust = src.baseline_trust_score;
            let trustClass = "trust-high";
            if (trust < 0.45) trustClass = "trust-low";
            else if (trust < 0.70) trustClass = "trust-mid";

            let domainLabel = src.url_or_filename;
            try {
                if (src.source_type === "web") {
                    domainLabel = new URL(src.url_or_filename).hostname.replace(/^www\./, '');
                }
            } catch (_) {}

            card.innerHTML = `
                <div class="source-card-top">
                    <span class="source-id-tag">${src.source_id}</span>
                    <span class="trust-badge-small ${trustClass}">Trust: ${(trust * 100).toFixed(0)}%</span>
                </div>
                <div class="source-card-title">${src.title || domainLabel}</div>
                <div class="source-card-meta">
                    <span>${domainLabel}</span>
                    <span>AI: ${(src.ai_probability_score * 100).toFixed(0)}%</span>
                </div>
            `;

            card.addEventListener("click", () => {
                focusSource(src.source_id);
            });

            sourcesList.appendChild(card);
        });
    }

    function renderDossier(data) {
        // Summary
        summaryText.textContent = data.synthesis.topic_summary || data.synthesis.summary || "";

        // Facts
        factsContainer.innerHTML = "";
        (data.synthesis.facts || []).forEach(fact => {
            const item = document.createElement("div");
            item.className = "fact-item";

            const supportingList = fact.supporting || [];
            const citeIds = fact.citations || Array.from(new Set(supportingList.map(s => s.source_id)));
            const citesHtml = citeIds.map(cid => `<span class="cite-chip" data-cid="${cid}">${cid}</span>`).join(" ");
            const quotesHtml = supportingList.map(q => `<div>"${q.quote || q.verbatim_quote || ''}" <span style="opacity: 0.6;">— [${q.source_id}]</span></div>`).join("");

            item.innerHTML = `
                <div class="fact-claim">${fact.statement}</div>
                <div class="citations-bar">${citesHtml}</div>
                <div class="quote-drawer">${quotesHtml}</div>
            `;

            item.addEventListener("click", (e) => {
                if (e.target.classList.contains("cite-chip")) {
                    const cid = e.target.getAttribute("data-cid");
                    focusSource(cid);
                    return;
                }
                const drawer = item.querySelector(".quote-drawer");
                if (drawer) drawer.classList.toggle("open");
                if (citeIds.length > 0) focusSource(citeIds[0]);
            });

            factsContainer.appendChild(item);
        });

        // Conflicts
        conflictsContainer.innerHTML = "";
        const conflictsList = data.synthesis.conflicts || [];
        if (conflictsList.length === 0) {
            conflictsContainer.innerHTML = `<div style="font-size: 0.82rem; color: #94a3b8; font-style: italic;">No contradictory claims detected across sources.</div>`;
        } else {
            conflictsList.forEach(c => {
                const card = document.createElement("div");
                card.className = "conflict-card";

                const claims = c.claims || [];
                const claimsHtml = claims.map(cl => `
                    <div class="conflict-claim">
                        • <strong>${cl.claim || cl.statement || ''}</strong> 
                        <span class="cite-chip" data-cid="${cl.source_id}">${cl.source_id}</span>
                        ${cl.quote ? `<div style="font-size: 0.74rem; opacity: 0.7; font-style: italic; margin-left: 12px;">"${cl.quote}"</div>` : ''}
                    </div>
                `).join("");

                card.innerHTML = `
                    <div class="conflict-topic">Disputed: ${c.topic} (${c.severity || 'MODERATE'})</div>
                    <div>${claimsHtml}</div>
                    ${c.note ? `<div style="font-size: 0.75rem; color: var(--accent-amber); margin-top: 6px;">Note: ${c.note}</div>` : ''}
                `;

                card.querySelectorAll(".cite-chip").forEach(chip => {
                    chip.addEventListener("click", (e) => {
                        e.stopPropagation();
                        focusSource(e.target.getAttribute("data-cid"));
                    });
                });

                card.addEventListener("click", (e) => {
                    if (e.target.classList.contains("cite-chip")) return;
                    if (claims.length > 0 && claims[0].source_id) {
                        focusSource(claims[0].source_id);
                    }
                });

                conflictsContainer.appendChild(card);
            });
        }

        // Missing Information (Dark Spots)
        missingContainer.innerHTML = "";
        const missingList = data.synthesis.missing_information || [];
        if (missingList.length === 0) {
            missingContainer.innerHTML = `<div style="font-size: 0.82rem; color: #94a3b8; font-style: italic;">No critical information gaps identified.</div>`;
        } else {
            missingList.forEach(m => {
                const card = document.createElement("div");
                card.className = "missing-card";
                card.innerHTML = `
                    <div class="missing-desc">⚠️ ${m.description}</div>
                    <div class="missing-reason">${m.why_expected || m.why_needed || ''} (${m.importance || 'HIGH'} priority)</div>
                `;
                missingContainer.appendChild(card);
            });
        }
    }

    // --- Cross-linking Helper ---
    function focusSource(sourceId) {
        document.querySelectorAll(".source-item-card").forEach(c => c.classList.remove("active"));
        const card = document.getElementById(`source-card-${sourceId}`);
        if (card) {
            card.classList.add("active");
            card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }

        scene.focusNodeById(sourceId);

        const src = state.lastAnalysis?.sources?.find(s => s.source_id === sourceId);
        if (src) {
            displayFloatingCard(src);
        }
    }

    function displayFloatingCard(src) {
        floatingCard.classList.remove("hidden");
        floatingSourceId.textContent = src.source_id;
        floatingTrustBadge.textContent = `Trust: ${(src.baseline_trust_score * 100).toFixed(0)}%`;
        floatingTitle.textContent = src.title || src.url_or_filename;
        floatingExcerpt.textContent = src.text_excerpt || "";
        floatingLink.href = src.url_or_filename.startsWith("http") ? src.url_or_filename : "#";
        if (src.source_type !== "web") {
            floatingLink.textContent = "Attached Document";
            floatingLink.style.pointerEvents = "none";
        } else {
            floatingLink.textContent = "Visit Source ↗";
            floatingLink.style.pointerEvents = "auto";
        }
    }

    closeFloatingCard.addEventListener("click", () => {
        floatingCard.classList.add("hidden");
        scene.resetHighlights();
        scene.focusOverview();
    });

    // Wire Scene Callbacks
    scene.onNodeClickCallback = (source) => {
        if (source) {
            focusSource(source.source_id);
        }
    };

    scene.onNodeHoverCallback = (source) => {
        // Ambient cursor feedback
    };

    // --- Module 4 Decision Support Submission (Multi-Evaluation Ledger) ---
    submitDecisionBtn.addEventListener("click", submitDecision);
    decisionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            submitDecision();
        }
    });

    async function submitDecision() {
        const decisionText = decisionInput.value.trim();
        if (decisionText.length < 3) {
            showToast("Decision Required", "Please enter your intended decision (at least 3 characters).", "warning");
            return;
        }

        if (!state.lastAnalysis) {
            showToast("Exploration Required", "Please perform an initial ground-truth exploration first.", "warning");
            return;
        }

        submitDecisionBtn.disabled = true;
        submitDecisionBtn.innerHTML = `<span>Evaluating...</span>`;

        try {
            const payload = {
                decision: decisionText,
                query: state.lastAnalysis.query,
                synthesis: state.lastAnalysis.synthesis,
                trusted_sources: state.lastAnalysis.debug?.trusted_sources || [],
                options: {
                    mock_mode: mockModeToggle.checked,
                }
            };

            const res = await fetch("/api/decide", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                const msg = errData?.error?.message || errData?.detail || `Server returned HTTP ${res.status}`;
                throw new Error(msg);
            }

            const data = await res.json();
            renderDecisionSupport(decisionText, data.decision_payload);

        } catch (err) {
            console.error(err);
            showToast("Decision Evaluation Failed", err.message, "error", 8000);
        } finally {
            submitDecisionBtn.disabled = false;
            submitDecisionBtn.innerHTML = `<span>Evaluate</span><span>→</span>`;
        }
    }

    // --- Append Multiple Decision Evaluations Beneath Each Other ---
    function renderDecisionSupport(decisionText, payload) {
        state.decisionCount = (state.decisionCount || 0) + 1;
        const count = state.decisionCount;

        const readiness = payload.decision_readiness || payload.readiness_level || "VERIFY_FIRST";
        let readinessClass = "readiness-verify";
        if (readiness === "GO") readinessClass = "readiness-go";
        else if (readiness === "PROCEED_WITH_CAUTION") readinessClass = "readiness-caution";

        const score = payload.overall_trust_score ?? payload.trust_score ?? 0.5;
        const comp = payload.trust_summary?.components || payload.component_scores || {};
        const checklist = payload.actionable_verification_checklist || payload.actionable_checklist || [];

        const checklistHtml = checklist.map((item, idx) => {
            const stepId = item.step_id || item.item_id || `step-${idx}`;
            const uniqueId = `chk-eval${count}-${stepId}`;
            return `
                <div class="check-item">
                    <input type="checkbox" class="check-box" id="${uniqueId}">
                    <label for="${uniqueId}" class="check-action">
                        <strong>[${item.urgency || 'MEDIUM'}]</strong> ${item.action}
                    </label>
                </div>
            `;
        }).join("");

        const entryCard = document.createElement("div");
        entryCard.className = "dossier-card decision-entry-card";
        entryCard.id = `decision-eval-card-${count}`;

        entryCard.innerHTML = `
            <div class="card-header">
                <span class="card-tag highlight-blue">DECISION EVALUATION #${count}</span>
                <span class="readiness-pill ${readinessClass}">${readiness.replace(/_/g, " ")}</span>
            </div>
            
            <div class="decision-context-box">Target Decision: "${decisionText}"</div>

            <div class="trust-metric-bar">
                <div class="metric-info">
                    <span class="metric-title">Deterministic Trust Score</span>
                    <span class="metric-number">${(score * 100).toFixed(1)}%</span>
                </div>
                <div class="progress-track">
                    <div class="progress-fill" style="width: ${Math.min(score * 100, 100)}%;"></div>
                </div>
                <div class="trust-components-grid">
                    <div class="comp-stat">Source Reliability: ${(comp.source_reliability * 100 || 0).toFixed(0)}%</div>
                    <div class="comp-stat">Consensus: ${(comp.consensus * 100 || 0).toFixed(0)}%</div>
                    <div class="comp-stat">Time Relevance: ${(comp.time_relevance * 100 || 0).toFixed(0)}%</div>
                </div>
            </div>

            <div class="checklist-section">
                <h4 class="sub-heading">ACTIONABLE VERIFICATION CHECKLIST</h4>
                <div class="checklist-items">${checklistHtml}</div>
            </div>
        `;

        decisionHistoryContainer.appendChild(entryCard);

        // Smoothly scroll Center Panel to the newly appended decision entry
        entryCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        // Clear input for next decision
        decisionInput.value = "";
    }
});
