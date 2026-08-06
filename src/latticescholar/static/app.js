"use strict";

const state = {
  config: null,
  papers: [],
  policies: [],
  selectedPapers: new Map(),
  selectedPolicies: new Map(),
  analyses: [],
  ideas: [],
  library: [],
  connectors: [],
  policySources: [],
  auth: null,
  account: null,
  projects: [],
  activeProjectId: null,
  searchHistory: [],
  policyCandidates: [],
  policySyncStatus: null,
  lastSearchResponse: null,
  analyzeMode: "text",
  paperFilter: "all",
  studentTasks: [],
  llmStatus: null,
  providerRegion: "all",
  lastDiscussion: null,
  ideaDocuments: [],
};

const pageMeta = {
  overview: ["科研工作台", "从一个问题开始，把研究过程完整留下"],
  projects: ["课题管理", "让每一次检索都服务于明确的研究问题"],
  explore: ["文献发现", "中文与英文分开检索，结果边界清楚可见"],
  analyze: ["论文精读", "先检查解析质量，再给出有页码证据的中文回答"],
  journals: ["投稿准备", "用真实发表样本判断期刊范围是否匹配"],
  policies: ["政策背景", "连接研究与战略语境，但不生硬贴标签"],
  ideas: ["研究设计", "把已有工作和证据缺口变成可验证问题"],
  discuss: ["课题研讨", "基于当前项目证据，形成可核验的下一步判断"],
  library: ["个人知识库", "沉淀可以复查、导出和迁移的科研资产"],
  students: ["科研任务台", "把模糊压力拆成今天能完成的交付物"],
  models: ["模型控制台", "安全连接多厂商模型，并看清每次任务的路由与消耗"],
  guide: ["使用指南", "按科研任务找答案，不必先学会所有配置"],
  account: ["账户与套餐", "清楚查看权益、额度与开源选择"],
  admin: ["系统管理", "管理用户权益与政策审核流程"],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[c]);
}

function safeUrl(value = "") {
  try {
    const url = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch { return "#"; }
}

function truncate(text = "", size = 500) { return text.length > size ? text.slice(0, size).trim() + "…" : text; }
function percent(value = 0) { return `${Math.round(Number(value || 0) * 100)}%`; }

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    let code = "";
    try { const body = await response.json(); message = body.detail || message; code = body.code || ""; } catch {}
    const error = new Error(message);
    error.status = response.status;
    error.code = code;
    throw error;
  }
  return response.headers.get("content-type")?.includes("application/json") ? response.json() : response.text();
}

// === Non-blocking Task Manager ===
const taskManager = {
  tasks: new Map(),
  nextId: 1,
  start(text = "正在处理…", buttonEl = null) {
    const id = this.nextId++;
    this.tasks.set(id, { text, buttonEl, startTime: Date.now() });
    if (buttonEl) {
      buttonEl.dataset.originalText = buttonEl.textContent;
      buttonEl.disabled = true;
      buttonEl.classList.add("task-running");
      buttonEl.innerHTML = `<span class="btn-spinner"></span>${text}`;
    }
    this._updateIndicator();
    return id;
  },
  finish(id, successMessage = null) {
    const task = this.tasks.get(id);
    if (task && task.buttonEl) {
      task.buttonEl.disabled = false;
      task.buttonEl.classList.remove("task-running");
      task.buttonEl.textContent = task.buttonEl.dataset.originalText || task.buttonEl.textContent;
    }
    if (task && successMessage) {
      toast(successMessage);
    } else if (task && this.tasks.size > 1) {
      toast(`✓ ${task.text.replace(/…$/, "")}完成`);
    }
    this.tasks.delete(id);
    this._updateIndicator();
  },
  _updateIndicator() {
    const indicator = $("#task-indicator");
    if (!indicator) return;
    if (this.tasks.size === 0) {
      indicator.classList.add("hidden");
      hideProgress();
    } else {
      const texts = [...this.tasks.values()].map(t => t.text);
      indicator.classList.remove("hidden");
      indicator.querySelector("strong").textContent = texts.length === 1
        ? texts[0]
        : `${texts.length} 个任务并行中`;
      indicator.querySelector("small").textContent = texts.join(" · ");
      showProgress(60);
    }
  }
};

function loading(show, text = "正在处理…") {
  // Legacy compatibility: non-blocking version
  if (show) {
    const indicator = $("#task-indicator");
    if (indicator) {
      indicator.classList.remove("hidden");
      indicator.querySelector("strong").textContent = text;
      indicator.querySelector("small").textContent = "可继续使用其他功能";
    }
    showProgress(50);
  } else {
    if (taskManager.tasks.size === 0) {
      const indicator = $("#task-indicator");
      if (indicator) indicator.classList.add("hidden");
      hideProgress();
    }
  }
}

function toast(message, kind = "ok") {
  const item = document.createElement("div");
  item.className = `toast ${kind === "error" ? "error" : ""}`;
  item.textContent = message;
  $("#toast-stack").appendChild(item);
  setTimeout(() => item.remove(), 3600);
}

function go(page) {
  $$(".page").forEach(el => el.classList.toggle("active", el.id === `page-${page}`));
  $$(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.page === page));
  $("#page-eyebrow").textContent = pageMeta[page][0];
  $("#page-title").textContent = pageMeta[page][1];
  window.scrollTo({top: 0, behavior: "smooth"});
  if (page === "library") loadLibrary();
  if (page === "projects") loadProjectWorkspace();
  if (page === "admin") loadAdminWorkspace();
  if (page === "students") renderStudentTasks();
  if (page === "models") loadModelStatus();
  if (page === "discuss") renderDiscussionProject();
}

function updateSelected() {
  $("#selected-paper-count").textContent = state.selectedPapers.size;
  $("#selected-policy-count").textContent = state.selectedPolicies.size;
}

async function initialize() {
  try {
    state.auth = await api("/api/auth/status");
    configureLogin(state.auth);
    if (state.auth.required && !state.auth.authenticated) {
      $("#login-screen").classList.remove("hidden");
      return;
    }
    $("#login-screen").classList.add("hidden");
    await initializeWorkspace();
  } catch (error) {
    $("#runtime-status").textContent = "服务连接失败";
    $("#llm-status").textContent = error.message;
    toast(error.message, "error");
  }
}

async function initializeWorkspace() {
  try {
    const [config, health, policies, connectors, policySources, account, projects, syncStatus, updateStatus, llmStatus] = await Promise.all([
      api("/api/config"), api("/api/health"), api("/api/policies"),
      api("/api/connectors"), api("/api/policy-sources"), api("/api/account"),
      api("/api/projects"), api("/api/policy-sync/status"), api("/api/update/check"), api("/api/llm/status")
    ]);
    state.config = config;
    state.policies = policies;
    state.connectors = connectors;
    state.policySources = policySources;
    state.account = account;
    state.projects = projects;
    state.policySyncStatus = syncStatus;
    state.llmStatus = llmStatus;
    restoreActiveProject();
    $("#runtime-status").textContent = config.auth_mode === "open" ? "开源社区版已就绪" : "托管服务已就绪";
    $("#llm-status").textContent = config.llm.enabled
      ? `${config.llm.active_count || 1} 个模型服务 · ${config.llm.routing || "自动路由"}`
      : "基础模式 · 未启用模型";
    $("#version-label").textContent = `v${config.version} · ${config.license}`;
    $("#policy-count").textContent = health.policy_records;
    const repositoryLink = $("#repository-link");
    if (config.repository_url) {
      repositoryLink.href = safeUrl(config.repository_url);
      repositoryLink.target = "_blank";
      repositoryLink.rel = "noopener";
      repositoryLink.textContent = "查看 GitHub ↗";
    } else {
      repositoryLink.removeAttribute("href");
      repositoryLink.textContent = "发布后配置仓库地址";
    }
    renderPolicies(policies);
    renderConnectors(connectors);
    renderPolicySources(policySources);
    renderAccount(account);
    renderProjects();
    renderProjectOptions();
    renderUpdateStatus(updateStatus);
    renderPolicySyncStatus(syncStatus);
    renderModelStatus(llmStatus);
    const wos = $("#source-wos");
    wos.disabled = !config.sources.web_of_science.enabled;
    if (wos.disabled) wos.closest("label").title = "先在服务端配置 WOS_API_KEY";
  } catch (error) {
    $("#runtime-status").textContent = "本地服务连接失败";
    $("#llm-status").textContent = error.message;
    toast(error.message, "error");
  }
}

function configureLogin(auth) {
  const accounts = auth.mode === "accounts";
  $("#email-login-form").classList.toggle("hidden", !accounts);
  $("#shared-login-form").classList.toggle("hidden", accounts);
  if (accounts) {
    $("#login-description").textContent = "使用邮箱验证码登录。无需记忆密码，所有功能对登录用户开放。";
    $("#login-message").textContent = auth.dev_auth ? "本地模式：验证码将直接显示在页面上。" : "验证码将发送到你的邮箱，10 分钟内有效。";
  } else {
    $("#login-description").textContent = "这是受保护的共享科研工作台。请输入访问密码继续。";
    $("#login-message").textContent = "登录会话通过 HttpOnly Cookie 安全保存。";
  }
}

function renderConnectors(connectors) {
  const ready = connectors.filter(item => item.ready).length;
  $("#connector-ready").textContent = `${ready}/${connectors.length} 条路径可用`;
  $("#connector-grid").innerHTML = connectors.map(item => {
    const labels = {official_api:"官方 API", licensed_api:"授权 API", authorized_or_import:"授权 / 导入", link_and_import:"原站 / 导入"};
    const query = encodeURIComponent($("#search-query").value.trim());
    let link = item.search_url;
    if (item.id === "google_scholar" && query) link += `scholar?q=${query}`;
    if (item.id === "pubmed" && query) link += `?term=${query}`;
    return `<article class="connector-card"><div class="connector-top"><h4>${escapeHtml(item.name)}</h4><span class="mode-badge ${item.ready ? "" : "pending"}">${escapeHtml(labels[item.mode] || item.mode)}</span></div><p>${escapeHtml(item.coverage)}</p><small>${escapeHtml(item.cost)}<br>${escapeHtml(item.workflow)}</small><a href="${safeUrl(link)}" target="_blank" rel="noopener">打开原平台 ↗</a></article>`;
  }).join("");
}

function renderPolicySources(items) {
  $("#policy-source-count").textContent = items.length;
  $("#policy-source-grid").innerHTML = items.map(source => `<article class="policy-source-card"><span>${escapeHtml(source.sector)}</span><h4>${escapeHtml(source.authority)}</h4><p>${escapeHtml(source.scope)}</p><a href="${safeUrl(source.portal_url)}" target="_blank" rel="noopener">进入官方政策源 ↗</a></article>`).join("");
  const syncSelect = $("#policy-sync-source");
  if (syncSelect) syncSelect.innerHTML = items.map(source => `<option value="${escapeHtml(source.id)}">${escapeHtml(source.authority)} · ${escapeHtml(source.sector)}</option>`).join("");
}

function restoreActiveProject() {
  const saved = Number(window.localStorage.getItem("latticescholar-active-project"));
  state.activeProjectId = state.projects.some(project => project.id === saved)
    ? saved : (state.projects[0]?.id || null);
}

function currentProject() {
  return state.projects.find(project => project.id === state.activeProjectId) || null;
}

function renderProjectOptions() {
  const options = state.projects.map(project => `<option value="${project.id}">${escapeHtml(project.name)}</option>`).join("");
  const searchSelect = $("#search-project");
  const librarySelect = $("#library-project");
  if (searchSelect) {
    searchSelect.innerHTML = `<option value="">不归入项目</option>${options}`;
    searchSelect.value = state.activeProjectId || "";
  }
  if (librarySelect) {
    const previous = librarySelect.value;
    librarySelect.innerHTML = `<option value="">全部项目</option>${options}`;
    librarySelect.value = state.projects.some(project => String(project.id) === previous) ? previous : "";
  }
  const active = currentProject();
  $("#active-project-label").textContent = active ? active.name : "未选择科研项目";
  $("#active-project-pill").classList.toggle("has-project", Boolean(active));
  renderDiscussionProject();
}

function renderProjects() {
  $("#project-count").textContent = state.projects.length;
  const container = $("#project-list");
  if (!state.projects.length) {
    container.className = "project-list empty-state";
    container.innerHTML = "<span>▦</span><h3>还没有科研项目</h3><p>先建立一个项目，后续检索和收藏会自动归档。</p>";
    renderProjectDetail(null);
    return;
  }
  const statusLabels = {active:"进行中", paused:"已暂停", completed:"已完成", archived:"已归档"};
  container.className = "project-list";
  container.innerHTML = state.projects.map(project => `<article class="project-card ${project.id === state.activeProjectId ? "active" : ""}">
    <button class="project-select" data-project-activate="${project.id}"><span class="status-dot"></span><div><strong>${escapeHtml(project.name)}</strong><p>${escapeHtml(truncate(project.research_question || "尚未填写研究问题", 100))}</p><small>${statusLabels[project.status] || project.status} · ${project.search_count} 次检索 · ${project.evidence_count} 条证据</small></div></button>
    <div class="project-card-actions"><button class="text-btn" data-project-archive="${project.id}">归档</button><button class="text-btn danger" data-project-delete="${project.id}">删除容器</button></div>
  </article>`).join("");
  renderProjectDetail(currentProject());
}

function renderProjectDetail(project) {
  const container = $("#project-detail");
  if (!project) {
    container.className = "panel project-detail empty-state";
    container.innerHTML = "<span>◎</span><h3>选择一个项目</h3><p>这里会展示项目问题、检索轨迹与已归档证据。</p>";
    return;
  }
  container.className = "panel project-detail";
  container.innerHTML = `<div class="project-detail-head"><div><span class="eyebrow">ACTIVE RESEARCH QUESTION</span><h2>${escapeHtml(project.name)}</h2></div><span class="local-badge">${project.search_count} 次检索 · ${project.evidence_count} 条证据</span></div>
    <div class="research-question"><strong>核心研究问题</strong><p>${escapeHtml(project.research_question || "尚未填写")}</p></div>
    ${project.description ? `<p class="project-description">${escapeHtml(project.description)}</p>` : ""}
    <div class="card-actions"><button class="btn btn-primary" data-project-search="${project.id}">围绕此问题检索 <span>→</span></button><button class="btn btn-secondary" data-project-complete="${project.id}">标记为已完成</button></div>`;
}

async function setActiveProject(projectId, notify = true) {
  const id = Number(projectId) || null;
  state.activeProjectId = state.projects.some(project => project.id === id) ? id : null;
  if (state.activeProjectId) window.localStorage.setItem("latticescholar-active-project", String(state.activeProjectId));
  else window.localStorage.removeItem("latticescholar-active-project");
  renderProjects();
  renderProjectOptions();
  await loadProjectWorkspace();
  if (notify && currentProject()) toast(`当前项目：${currentProject().name}`);
}

async function createProject(event) {
  event.preventDefault();
  try {
    const project = await api("/api/projects", {method:"POST", body:JSON.stringify({
      name:$("#project-name").value.trim(), research_question:$("#project-question").value.trim(), description:$("#project-description").value.trim()
    })});
    state.projects.unshift(project);
    event.target.reset();
    await setActiveProject(project.id, false);
    toast("科研项目已创建，后续检索将自动归档");
  } catch (error) { toast(error.message, "error"); }
}

async function loadProjectWorkspace() {
  const project = currentProject();
  if (!project) {
    $("#project-history-count").textContent = "0 次";
    $("#project-evidence-count").textContent = "0 条";
    $("#project-history").className = "compact-list empty-state";
    $("#project-history").innerHTML = "<span>⌕</span><p>当前项目还没有检索记录。</p>";
    $("#project-evidence").className = "compact-list empty-state";
    $("#project-evidence").innerHTML = "<span>▣</span><p>当前项目还没有归档证据。</p>";
    return;
  }
  try {
    const [detail, history, evidence] = await Promise.all([
      api(`/api/projects/${project.id}`), api(`/api/search-history?project_id=${project.id}`), api(`/api/library?project_id=${project.id}`)
    ]);
    state.projects = state.projects.map(item => item.id === detail.id ? detail : item);
    state.searchHistory = history;
    renderProjects();
    renderSearchHistory(history);
    renderProjectEvidence(evidence);
  } catch (error) { toast(error.message, "error"); }
}

function renderSearchHistory(items) {
  $("#project-history-count").textContent = `${items.length} 次`;
  const container = $("#project-history");
  if (!items.length) { container.className = "compact-list empty-state"; container.innerHTML = "<span>⌕</span><p>当前项目还没有检索记录。</p>"; return; }
  container.className = "compact-list";
  container.innerHTML = items.map(item => `<article class="trace-item"><div><strong>${escapeHtml(item.query)}</strong><p>${item.sources.map(escapeHtml).join(" · ")} · ${item.result_count} 条结果 · ${item.elapsed_ms} ms</p><small>${escapeHtml(new Date(item.created_at).toLocaleString())}${item.cache_hit ? " · 缓存命中" : ""}</small></div><div><button class="text-btn" data-history-replay="${item.id}">复现</button><button class="text-btn danger" data-history-delete="${item.id}">删除</button></div></article>`).join("");
}

function renderProjectEvidence(items) {
  $("#project-evidence-count").textContent = `${items.length} 条`;
  const container = $("#project-evidence");
  if (!items.length) { container.className = "compact-list empty-state"; container.innerHTML = "<span>▣</span><p>当前项目还没有归档证据。</p>"; return; }
  container.className = "compact-list";
  container.innerHTML = items.slice(0, 30).map(item => `<article class="trace-item evidence-trace"><div class="trace-content"><div class="evidence-type-row"><span class="kind-label">${escapeHtml(item.kind.toUpperCase())}</span></div><strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong><small>${escapeHtml(new Date(item.created_at).toLocaleString())}</small></div></article>`).join("");
}

async function projectActions(event) {
  const activate = event.target.closest("[data-project-activate]");
  const archive = event.target.closest("[data-project-archive]");
  const remove = event.target.closest("[data-project-delete]");
  const search = event.target.closest("[data-project-search]");
  const complete = event.target.closest("[data-project-complete]");
  if (activate) return setActiveProject(activate.dataset.projectActivate);
  if (search) { await setActiveProject(search.dataset.projectSearch, false); $("#search-query").value = currentProject()?.research_question || ""; go("explore"); return; }
  try {
    if (archive || complete) {
      const id = Number((archive || complete).dataset.projectArchive || (archive || complete).dataset.projectComplete);
      await api(`/api/projects/${id}`, {method:"PATCH", body:JSON.stringify({status:archive ? "archived" : "completed"})});
      state.projects = await api("/api/projects");
      if (!state.projects.some(project => project.id === state.activeProjectId)) state.activeProjectId = state.projects[0]?.id || null;
      renderProjects(); renderProjectOptions(); await loadProjectWorkspace();
      toast(archive ? "项目已归档，证据仍然保留" : "项目已标记为完成");
    }
    if (remove) {
      const id = Number(remove.dataset.projectDelete);
      if (!window.confirm("删除项目容器？检索记录和证据不会被删除，但会变为未归类。")) return;
      await api(`/api/projects/${id}`, {method:"DELETE"});
      state.projects = state.projects.filter(project => project.id !== id);
      if (state.activeProjectId === id) state.activeProjectId = state.projects[0]?.id || null;
      renderProjects(); renderProjectOptions(); await loadProjectWorkspace();
      toast("项目容器已删除，原有证据已保留");
    }
  } catch (error) { toast(error.message, "error"); }
}

async function historyActions(event) {
  const replay = event.target.closest("[data-history-replay]");
  const remove = event.target.closest("[data-history-delete]");
  const item = state.searchHistory.find(run => run.id === Number((replay || remove)?.dataset.historyReplay || (replay || remove)?.dataset.historyDelete));
  if (!item) return;
  if (replay) {
    $("#search-query").value = item.query;
    $("#year-from").value = item.year_from || "";
    $("#year-to").value = item.year_to || "";
    $("#search-limit").value = String(item.requested_limit);
    $$('input[name="source"]').forEach(input => { input.checked = item.sources.includes(input.value); });
    $("#search-project").value = item.project_id || "";
    go("explore");
    toast("检索条件已恢复，点击“开始检索”即可复现");
  } else {
    await api(`/api/search-history/${item.id}`, {method:"DELETE"});
    await loadProjectWorkspace();
    toast("检索记录已删除");
  }
}

function renderUpdateStatus(status) {
  const container = $("#update-status");
  const label = status.update_available ? "发现新版本" : "版本状态";
  let title = `当前版本 v${escapeHtml(status.current_version || state.config?.version || "—")}`;
  let detail = "尚未配置 GitHub 仓库地址，发布后即可自动检查 Release。";
  let action = "";
  if (status.status === "ok") {
    detail = status.update_available ? `最新版本 ${escapeHtml(status.latest_version)} 已发布，建议阅读变更后升级。` : `已是最新版本${status.latest_version ? `（${escapeHtml(status.latest_version)}）` : ""}。`;
    if (status.release_url) action = `<a class="btn btn-secondary" href="${safeUrl(status.release_url)}" target="_blank" rel="noopener">查看 Release ↗</a>`;
  } else if (status.status === "no_release") detail = "仓库尚未发布正式 Release。";
  else if (status.status === "error") detail = "暂时无法连接 GitHub，稍后会重新检查。";
  container.innerHTML = `<div><span class="eyebrow">VERSION HEALTH</span><h3>${title}</h3><p>${detail}</p></div><div class="update-actions"><span class="local-badge ${status.update_available ? "warning" : ""}">${label}</span>${action}</div>`;
}

function renderPolicySyncStatus(status) {
  state.policySyncStatus = status;
  $("#policy-pending-count").textContent = status.pending || 0;
  $("#policy-approved-count").textContent = status.approved_dynamic || 0;
  $("#policy-sync-note").textContent = status.last_run
    ? `最近运行：${new Date(status.last_run.completed_at).toLocaleString()} · ${status.last_run.status} · 发现 ${status.last_run.discovered} 条`
    : "同步任务尚未运行";
}

function canManagePolicies() {
  return state.account?.role === "admin" || state.account?.mode === "community";
}

async function loadAdminWorkspace() {
  if (!canManagePolicies()) return;
  try {
    const [candidates, status] = await Promise.all([api("/api/admin/policy-candidates?status=pending"), api("/api/policy-sync/status")]);
    state.policyCandidates = candidates;
    renderPolicyCandidates(candidates);
    renderPolicySyncStatus(status);
  } catch (error) { toast(error.message, "error"); }
}

function renderPolicyCandidates(items) {
  const container = $("#policy-candidate-list");
  if (!items.length) { container.className = "candidate-list empty-state"; container.innerHTML = "<span>▤</span><h3>没有待审核候选</h3><p>政策不会未经核验自动进入用户政策库。</p>"; return; }
  container.className = "candidate-list";
  container.innerHTML = items.map(item => `<article class="candidate-card" data-candidate-id="${item.id}">
    <div class="candidate-meta"><span class="tag source-tag">${escapeHtml(item.source_id)}</span><span>${escapeHtml(new Date(item.discovered_at).toLocaleString())}</span><a href="${safeUrl(item.url)}" target="_blank" rel="noopener">核验原文 ↗</a></div>
    <div class="candidate-fields"><label class="field"><span>正式标题</span><input data-candidate-field="title" value="${escapeHtml(item.title)}"></label><label class="field"><span>发布机构</span><input data-candidate-field="issuer" value="${escapeHtml(item.issuer)}"></label><label class="field"><span>发布日期（YYYY-MM-DD）</span><input data-candidate-field="published_at" value="${escapeHtml(item.published_at)}"></label><label class="field wide"><span>官方原文 URL</span><input data-candidate-field="url" value="${escapeHtml(item.url)}"></label><label class="field wide"><span>核验后摘要</span><textarea rows="3" data-candidate-field="summary">${escapeHtml(item.summary)}</textarea></label><label class="field wide"><span>政策信号（逗号分隔）</span><input data-candidate-field="signals" value="${escapeHtml(item.signals.join("，"))}"></label><label class="field wide"><span>标签（逗号分隔）</span><input data-candidate-field="tags" value="${escapeHtml(item.tags.join("，"))}"></label></div>
    <div class="candidate-actions"><button class="btn btn-primary" data-candidate-approve="${item.id}">核验通过并发布</button><button class="btn btn-secondary" data-candidate-reject="${item.id}">拒绝候选</button><small>通过后会立即进入政策雷达；条目变化时会重新转为待审核。</small></div>
  </article>`).join("");
}

async function syncPolicies() {
  const syncTaskId = taskManager.start("政策源同步中…");
  try {
    const result = await api("/api/admin/policies/sync", {method:"POST", body:JSON.stringify({source_ids:[$("#policy-sync-source").value]})});
    renderPolicySyncStatus(result.status);
    await loadAdminWorkspace();
    const run = result.runs[0];
    toast(run.status === "ok" ? `发现 ${run.discovered} 条候选，新增或变化 ${run.changed} 条` : `同步未完成：${run.error}`, run.status === "ok" ? "ok" : "error");
  } catch (error) { toast(error.message, "error"); }
  finally { taskManager.finish(syncTaskId); }
}

async function reviewPolicyCandidate(event) {
  const approve = event.target.closest("[data-candidate-approve]");
  const reject = event.target.closest("[data-candidate-reject]");
  if (!approve && !reject) return;
  const card = event.target.closest("[data-candidate-id]");
  const value = field => card.querySelector(`[data-candidate-field="${field}"]`)?.value.trim() || "";
  const split = field => value(field).split(/[,，]/).map(item => item.trim()).filter(Boolean);
  const body = reject ? {action:"reject"} : {action:"approve", title:value("title"), issuer:value("issuer"), published_at:value("published_at"), url:value("url"), summary:value("summary"), signals:split("signals"), tags:split("tags")};
  try {
    await api(`/api/admin/policy-candidates/${card.dataset.candidateId}/review`, {method:"POST", body:JSON.stringify(body)});
    const [policies, health] = await Promise.all([api("/api/policies"), api("/api/health")]);
    state.policies = policies;
    renderPolicies(policies);
    $("#policy-count").textContent = health.policy_records;
    await loadAdminWorkspace();
    toast(reject ? "候选已拒绝" : "政策已核验并发布");
  } catch (error) { toast(error.message, "error"); }
}

async function sharedLogin(event) {
  event.preventDefault();
  const message = $("#login-message");
  message.textContent = "正在验证…";
  try {
    await api("/api/auth/login", {method:"POST", body:JSON.stringify({password:$("#login-password").value})});
    $("#login-screen").classList.add("hidden");
    await initializeWorkspace();
  } catch (error) {
    message.textContent = error.message;
  }
}

async function emailLogin(event) {
  event.preventDefault();
  const message = $("#login-message");
  const email = $("#login-email").value.trim().toLowerCase();
  try {
    if (!$("#code-step").classList.contains("hidden")) {
      message.textContent = "正在验证邮箱…";
      const result = await api("/api/auth/verify-code", {method:"POST", body:JSON.stringify({email, code:$("#login-code").value.trim()})});
      state.account = result.user;
      $("#login-screen").classList.add("hidden");
      await initializeWorkspace();
      toast("登录成功，欢迎回来");
      return;
    }
    message.textContent = "正在发送验证码…";
    const result = await api("/api/auth/request-code", {method:"POST", body:JSON.stringify({email})});
    $("#email-step").classList.add("hidden");
    $("#code-step").classList.remove("hidden");
    $("#login-code").disabled = false;
    $("#code-target").textContent = email;
    $("#login-code").focus();
    message.textContent = result.dev_code ? `本地验证码：${result.dev_code}` : "验证码已发送，请检查收件箱与垃圾邮件。";
  } catch (error) { message.textContent = error.message; }
}

function resetEmailLogin() {
  $("#email-step").classList.remove("hidden");
  $("#code-step").classList.add("hidden");
  $("#login-code").value = "";
  $("#login-code").disabled = true;
  $("#login-message").textContent = "验证码 10 分钟有效；登录状态通过 HttpOnly Cookie 安全保存。";
}

function formatExpiry(value) {
  if (!value) return "长期有效";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "长期有效" : `有效至 ${date.toLocaleString("zh-CN", {year:"numeric", month:"short", day:"numeric"})}`;
}

function renderAccount(account) {
  const entitlement = account.entitlement || {};
  const planNames = {community:"社区版", user:"注册用户", admin:"管理员", anonymous:"未登录"};
  const planName = planNames[entitlement.plan] || String(entitlement.plan || "—");
  $("#account-email").textContent = account.email || "开源社区版 · 自行部署";
  $("#account-entitlement").textContent = entitlement.label || "全部功能可用";
  $("#account-plan").textContent = planName;
  $("#account-expiry").textContent = "全功能可用";
  $("#plan-pill-label").textContent = planName;
  $("#overview-plan").textContent = planName;
  $("#overview-plan-note").textContent = "全功能可用";
  $("#admin-nav").classList.toggle("hidden", account.role !== "admin" && account.mode !== "community");
  $("#logout-button").classList.toggle("hidden", !account.email);
  $("#usage-grid").innerHTML = "";
  $("#pricing-grid").innerHTML = "";
}

async function logout() {
  await api("/api/auth/logout", {method:"POST", body:"{}"});
  window.location.reload();
}

async function importBibliography(event) {
  event.preventDefault();
  const file = $("#bibliography-file").files[0];
  if (!file) return toast("请选择题录文件", "error");
  const form = new FormData();
  form.append("file", file);
  form.append("source_name", $("#import-source").value);
  const projectId = Number($("#search-project").value) || null;
  if (projectId) form.append("project_id", String(projectId));
  const importTaskId = taskManager.start("题录导入中…");
  try {
    const response = await fetch("/api/import/bibliography", {method:"POST", body:form});
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail || "题录导入失败"); }
    renderPapers(await response.json());
    if (projectId) await loadProjectWorkspace();
    toast(`已导入 ${file.name}`);
  } catch (error) { toast(error.message, "error"); }
  finally { taskManager.finish(importTaskId); }
}

function paperKey(paper) { return paper.doi || paper.id; }

function renderPapers(response) {
  state.lastSearchResponse = response;
  state.papers = sortPapers(response.papers, $("#search-sort")?.value || "relevance");
  const facets = response.facets || {};
  $("#facet-all").textContent = facets.all ?? response.papers.length;
  $("#facet-zh").textContent = facets.zh ?? response.papers.filter(p=>p.language === "zh").length;
  $("#facet-en").textContent = facets.en ?? response.papers.filter(p=>p.language === "en").length;
  $("#facet-mixed").textContent = facets.mixed ?? response.papers.filter(p=>p.language === "mixed").length;
  $("#facet-abstract").textContent = facets.with_abstract ?? response.papers.filter(p=>p.abstract?.length >= 20).length;
  const statuses = Object.entries(response.source_status).map(([k,v]) => `${k}: ${v}`).join(" · ");
  const summary = $("#search-summary");
  const quality = response.quality || {};
  summary.classList.remove("hidden");
  summary.innerHTML = `<div class="search-summary-head"><div><strong>${response.papers.length} 条结果</strong><span>${facets.with_abstract ?? 0} 条含摘要 · ${facets.citation_only ?? 0} 条仅题录 · ${response.elapsed_ms} ms${response.cache_hit ? " · 本地缓存" : ""}</span></div>${quality.label ? `<b class="retrieval-grade grade-${quality.label === "高" ? "high" : quality.label === "中" ? "medium" : "low"}">检索可信度 ${escapeHtml(quality.label)}</b>` : ""}</div>${quality.label ? `<div class="retrieval-audit"><span><b>${quality.successful_sources || 0}/${quality.requested_sources || 0}</b>数据源成功</span><span><b>${percent(quality.abstract_coverage)}</b>摘要覆盖</span><span><b>${percent(quality.doi_coverage)}</b>DOI 覆盖</span><span><b>${quality.corroborated_records || 0}</b>多源印证</span><span><b>${quality.deduplicated_records || 0}</b>重复合并</span></div>` : ""}<small>${escapeHtml(statuses)}</small>${quality.interpretation ? `<p class="quality-interpretation">${escapeHtml(quality.interpretation)}</p>` : ""}${response.notices?.length ? `<details><summary>查看检索提醒</summary><p>${response.notices.map(escapeHtml).join(" ")}</p></details>` : ""}`;
  $("#search-tools").classList.toggle("hidden", !response.papers.length);
  const container = $("#search-results");
  if (!response.papers.length) {
    container.className = "result-list empty-state";
    container.innerHTML = `<span>∅</span><h3>没有获得可用结果</h3><p>${escapeHtml(response.notices.join(" "))}</p>`;
    return;
  }
  const visible = state.papers.filter(paper => {
    if (["zh", "en", "mixed"].includes(state.paperFilter)) return paper.language === state.paperFilter;
    if (state.paperFilter === "abstract") return paper.abstract?.length >= 20;
    return true;
  });
  if (!visible.length) {
    container.className = "result-list empty-state";
    container.innerHTML = '<span>∅</span><h3>这个分组暂时没有结果</h3><p>切换“全部”，或调整语言与摘要筛选后重新检索。</p>';
    return;
  }
  container.className = "result-list";
  container.innerHTML = visible.map((paper, index) => {
    const key = paperKey(paper);
    const selected = state.selectedPapers.has(key);
    const meta = [paper.year, paper.venue, paper.authors?.slice(0,3).join(", ")].filter(Boolean);
    const hasAbstract = paper.abstract?.trim().length >= 20;
    const languageLabel = paper.language === "zh" ? "中文" : paper.language === "en" ? "English" : paper.language === "mixed" ? "中英混合" : "语言待核验";
    return `<article class="paper-card ${hasAbstract ? "has-abstract" : "citation-record"}">
      <div class="card-top"><div><div class="metadata"><span class="tag">#${index + 1}</span><span class="tag language-tag">${languageLabel}</span>${paper.sources.map(s=>`<span class="tag source-tag">${escapeHtml(s)}</span>`).join("")}${paper.open_access === true ? '<span class="tag oa-tag">开放获取</span>' : ""}${!hasAbstract ? '<span class="tag record-tag">仅题录</span>' : ""}</div><h3>${escapeHtml(paper.title)}</h3></div><div class="score-ring" style="--score:${percent(paper.score)}"><b>${percent(paper.score)}</b></div></div>
      <div class="metadata">${meta.map(x=>`<span>${escapeHtml(x)}</span>`).join("<span>·</span>")}${paper.citation_count != null ? `<span>·</span><span>引用信号 ${paper.citation_count}</span>` : ""}${paper.doi ? `<span>·</span><span>DOI ${escapeHtml(paper.doi)}</span>` : ""}</div>
      ${hasAbstract ? `<p class="abstract">${escapeHtml(truncate(paper.abstract, 650))}</p>` : ""}
      <div class="card-actions">${paper.url ? `<a href="${safeUrl(paper.url)}" target="_blank" rel="noopener">${hasAbstract ? "查看来源" : "前往来源获取原文"} ↗</a>` : ""}${hasAbstract ? `<button class="text-btn" data-paper-analyze="${escapeHtml(key)}">中文精读</button>` : ""}<button class="text-btn" data-paper-select="${escapeHtml(key)}">${selected ? "✓ 已加入研究设计" : "+ 研究设计"}</button><button class="text-btn" data-paper-save="${escapeHtml(key)}">收藏题录</button>${paper.doi ? `<button class="text-btn" data-paper-cite="${escapeHtml(key)}">导出引用</button>` : ""}</div>
    </article>`;
  }).join("");
}

function sortPapers(items, mode) {
  const papers = [...items];
  if (mode === "newest") papers.sort((a, b) => (b.year || 0) - (a.year || 0) || (b.score || 0) - (a.score || 0));
  else if (mode === "citations") papers.sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0) || (b.score || 0) - (a.score || 0));
  else if (mode === "completeness") papers.sort((a,b)=>(Boolean(b.abstract)-Boolean(a.abstract)) || ((b.open_access===true)-(a.open_access===true)) || (b.score||0)-(a.score||0));
  else papers.sort((a, b) => (b.score || 0) - (a.score || 0));
  return papers;
}

function rerenderSortedPapers() {
  if (!state.lastSearchResponse) return;
  renderPapers({...state.lastSearchResponse, papers:state.lastSearchResponse.papers});
}

async function submitSearch(event) {
  event.preventDefault();
  const sources = $$('input[name="source"]:checked').map(el => el.value);
  if (!sources.length) return toast("请至少选择一个数据源", "error");
  const yearFrom = Number($("#year-from").value) || null;
  const yearTo = Number($("#year-to").value) || null;
  if (yearFrom && yearTo && yearFrom > yearTo) return toast("起始年份不能晚于截止年份", "error");
  const body = {
    query: $("#search-query").value.trim(),
    english_query: $("#search-query-en").value.trim(),
    limit: Number($("#search-limit").value),
    sources,
    year_from: yearFrom,
    year_to: yearTo,
    language: $("#search-language").value,
    has_abstract: $("#search-abstract").value === "any" ? null : $("#search-abstract").value === "yes",
    open_access_only: $("#open-access-only").checked,
    min_citations: Number($("#min-citations").value) || 0,
    sort_by: $("#search-sort").value,
    project_id: Number($("#search-project").value) || null,
  };
  state.paperFilter = "all";
  $$("#paper-tabs button").forEach(button=>button.classList.toggle("active", button.dataset.paperFilter === "all"));
  const searchBtn = event.target.querySelector("button[type='submit']") || event.submitter;
  const searchTaskId = taskManager.start("文献检索中…", searchBtn);
  try {
    renderPapers(await api("/api/search", {method:"POST", body:JSON.stringify(body)}));
    if (body.project_id) await loadProjectWorkspace();
  }
  catch (error) { toast(`检索失败：${error.message}`, "error"); }
  finally { taskManager.finish(searchTaskId); }
}

function findPaper(key) { return state.papers.find(p => paperKey(p) === key) || state.selectedPapers.get(key); }

async function saveItem(kind, externalId, title, payload) {
  const projectId = state.activeProjectId || null;
  await api("/api/library", {method:"POST", body:JSON.stringify({kind, external_id:externalId, title, payload, note:"", project_id:projectId})});
  if (projectId) await loadProjectWorkspace();
  toast(projectId ? `已保存到“${currentProject()?.name}”证据库` : "已保存到本地证据库");
}

function setupPaperActions(event) {
  const analyze = event.target.closest("[data-paper-analyze]");
  const select = event.target.closest("[data-paper-select]");
  const save = event.target.closest("[data-paper-save]");
  const cite = event.target.closest("[data-paper-cite]");
  const button = analyze || select || save || cite;
  if (!button) return;
  const key = button.dataset.paperAnalyze || button.dataset.paperSelect || button.dataset.paperSave || button.dataset.paperCite;
  const paper = findPaper(key);
  if (!paper) return;
  if (cite) {
    const authors = paper.authors?.slice(0, 3).join(", ") || "Unknown";
    const citation = `${authors}. ${paper.title}. ${paper.venue || ""}${paper.year ? ` (${paper.year})` : ""}${paper.doi ? `. DOI: ${paper.doi}` : ""}`;
    navigator.clipboard.writeText(citation).then(() => toast("引用信息已复制到剪贴板")).catch(() => toast("复制失败", "error"));
    return;
  }
  if (analyze) {
    $("#analyze-title").value = paper.title;
    $("#analyze-abstract").value = paper.abstract;
    go("analyze");
  } else if (select) {
    if (state.selectedPapers.has(key)) state.selectedPapers.delete(key); else state.selectedPapers.set(key, paper);
    updateSelected();
    select.textContent = state.selectedPapers.has(key) ? "✓ 已加入 Idea Lab" : "+ 加入 Idea Lab";
    toast(state.selectedPapers.has(key) ? "已加入 Idea Lab" : "已移出 Idea Lab");
  } else if (save) {
    saveItem("paper", key, paper.title, paper).catch(e=>toast(e.message,"error"));
  }
}

function analysisHtml(result) {
  const confidenceLabels = {low:"置信度低 · 信息不足", medium:"置信度中等", high:"置信度高"};
  const modeLabels = {heuristic:"规则抽取", llm:"深度分析"};
  const qualityLabels = {high:"提取质量高",medium:"提取质量中等",low:"提取质量偏低",unknown:"质量未评估"};
  const methodLabels = {pdfplumber_layout:"Apache 核心版面解析",pymupdf4llm_markdown:"可选高级 Markdown 解析",pymupdf_blocks:"可选高级版面块解析", "pymupdf_blocks+ocr":"可选高级版面块 + OCR", pypdf_layout_fallback:"兼容版面解析",text_input:"文本输入"};
  const document = result.document ? `<div class="answer-source-grid"><span><b>${result.document.pages_parsed}/${result.document.pages_total}</b><small>解析页数</small></span><span><b>${Number(result.document.quality_score || 0).toFixed(2)}</b><small>提取质量</small></span><span><b>${escapeHtml(result.document.detected_language)}</b><small>原文语言</small></span><span><b>${result.document.ocr_used ? "已启用" : "未启用"}</b><small>OCR</small></span></div><p>${result.document.sections_found?.length ? `识别章节：${result.document.sections_found.map(escapeHtml).join("、")}` : "未稳定识别章节标题，请重点核对多栏、图表与参考文献边界。"}</p><small>${escapeHtml(methodLabels[result.document.method] || result.document.method)} · ${result.document.char_count.toLocaleString()} 字符${result.document.truncated ? " · 内容已按上限截取" : ""}</small>` : `<p>本次使用粘贴文本回答。</p>`;
  const hasUserFocus = (result.key_questions || []).some(item => item.key === "user_focus");
  const questions = (result.key_questions || []).map((item,index)=>{
    const points = item.points?.length ? item.points : [{title:"核心结论",detail:item.answer,locations:[]}];
    const pointList = points.map((point,pointIndex)=>`<li><span class="answer-point-no">${pointIndex+1}</span><div><strong>${escapeHtml(point.title)}</strong><p>${escapeHtml(point.detail)}</p>${point.locations?.length ? `<div class="answer-locations">${point.locations.map(location=>`<span>${escapeHtml(location)}</span>`).join("")}</div>` : ""}</div></li>`).join("");
    const evidence = item.evidence?.length ? `<details class="answer-evidence"><summary>核对原文依据（${item.evidence.length}）</summary>${item.evidence.map(e=>`<blockquote><span>${escapeHtml(e.location || "原文")}</span>${escapeHtml(e.quote)}</blockquote>`).join("")}</details>` : "";
    const isUserFocus = item.key === "user_focus";
    const cardClass = isUserFocus ? "question-card answer-card user-focus-card" : "question-card answer-card";
    const numLabel = isUserFocus ? `<span class="user-focus-badge">YOUR Q</span>` : `<div class="question-no">0${index+1}</div>`;
    return `<article class="${cardClass}">${numLabel}<div class="question-body"><h4>${escapeHtml(item.question)}</h4><div class="direct-answer"><span>${isUserFocus ? "针对性回答" : "结论"}</span><p>${escapeHtml(item.answer)}</p></div><ol class="answer-points">${pointList}</ol>${evidence}</div></article>`;
  }).join("");
  const sectionTitle = hasUserFocus ? "论文深度剖析" : "论文四问";
  const warnings = (result.warnings || []).map(item=>`<li>${escapeHtml(item)}</li>`).join("");
  return `<div class="answer-head"><h3>${sectionTitle}</h3><div><span>${escapeHtml(modeLabels[result.mode] || result.mode)}</span><span>${escapeHtml(confidenceLabels[result.confidence] || result.confidence)}</span>${result.document ? `<span class="quality-${escapeHtml(result.document.quality)}">${escapeHtml(qualityLabels[result.document.quality] || result.document.quality)}</span>` : ""}</div></div>
    <section class="key-question-section"><div class="question-grid">${questions || `<article class="question-card answer-card"><div class="question-body"><h4>当前结果缺少四问结构</h4><p>请重新提交论文进行分析。</p></div></article>`}</div></section>
    <details class="analysis-source-info"><summary>解析信息与回答边界</summary><div>${document}${warnings ? `<ul>${warnings}</ul>` : ""}</div></details>
    <div class="card-actions"><button class="text-btn" id="save-analysis">保存到证据库</button><button class="text-btn" id="copy-analysis">复制四问回答</button><button class="text-btn" id="new-analysis">重新分析论文</button></div>`;
}

function renderPdfSelection() {
  const file = $("#pdf-file").files[0];
  const status = $("#pdf-file-status");
  if (!file) { status.classList.add("hidden"); return; }
  const size = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
  $("#pdf-upload-zone").classList.add("has-file");
  $("#pdf-upload-title").textContent = file.name;
  $("#pdf-upload-note").textContent = `${size} · 点击可重新选择`;
  status.classList.remove("hidden");
  status.innerHTML = `<span>✓</span><div><strong>已就绪：先做版面重排，再进行中文分析</strong><small>自动去除重复页眉页脚并尝试修复断词；扫描页会检测本机 OCR。公式、复杂表格与图像结论仍需回看原文。</small></div>`;
}

async function submitAnalysis(event) {
  event.preventDefault();
  const submitBtn = event.target.querySelector("button[type='submit']") || event.submitter;
  const taskId = taskManager.start(state.analyzeMode === "pdf" ? "论文解析中…" : "深度分析中…", submitBtn);
  try {
    let result;
    if (state.analyzeMode === "pdf") {
      const file = $("#pdf-file").files[0];
      if (!file) throw new Error("请选择 PDF 文件");
      const form = new FormData(); form.append("file", file);
      form.append("research_question", $("#analysis-question").value);
      form.append("use_llm", $("#analysis-use-llm").checked);
      const response = await fetch("/api/analyze/pdf", {method:"POST", body:form});
      if (!response.ok) { const b = await response.json(); throw new Error(b.detail || "PDF 分析失败"); }
      result = await response.json();
    } else {
      const abstract = $("#analyze-abstract").value.trim();
      if (abstract.length < 20) throw new Error("请提供至少 20 个字符的摘要或文本");
      result = await api("/api/analyze", {method:"POST", body:JSON.stringify({title:$("#analyze-title").value,abstract,research_question:$("#analysis-question").value,use_llm:$("#analysis-use-llm").checked})});
    }
    state.analyses.unshift(result);
    const container = $("#analysis-result"); container.className = "panel result-panel"; container.innerHTML = analysisHtml(result);
    $("#analysis-layout").classList.add("has-result");
    container.scrollIntoView({behavior:"smooth",block:"start"});
    $("#save-analysis").onclick = () => saveItem("analysis", `analysis-${Date.now()}`, $("#analyze-title").value || "论文分析", result).catch(e=>toast(e.message,"error"));
    const copyBtn = $("#copy-analysis");
    if (copyBtn) copyBtn.onclick = () => {
      const quickRead = (result.key_questions || []).map((item,index)=>{
        const points = item.points?.length ? item.points : [{title:"核心结论",detail:item.answer}];
        return `${index+1}. ${item.question}\n${item.answer}\n${points.map((point,i)=>`   ${i+1}) ${point.title}：${point.detail}`).join("\n")}`;
      }).join("\n\n");
      const text = `【论文四问｜中文回答】\n\n${quickRead}`;
      navigator.clipboard.writeText(text).then(()=>toast("分析结果已复制到剪贴板")).catch(()=>toast("复制失败，请手动选择复制","error"));
    };
    const newAnalysisBtn = $("#new-analysis");
    if (newAnalysisBtn) newAnalysisBtn.onclick = () => {
      $("#analysis-layout").classList.remove("has-result");
      $("#analyze-form").scrollIntoView({behavior:"smooth",block:"start"});
    };
  } catch (error) { toast(error.message, "error"); }
  finally { taskManager.finish(taskId); }
}

function renderJournals(items) {
  const container = $("#journal-results");
  if (!items.length) { container.className="result-list empty-state"; container.innerHTML="<span>∅</span><h3>没有形成候选</h3><p>尝试使用更完整的英文标题与摘要。</p>"; return; }
  container.className = "result-list";
  container.innerHTML = items.map((j,index)=>`<article class="journal-card"><div class="card-top"><div><div class="metadata"><span class="tag">候选 ${index+1}</span><span class="tag source-tag">Multi-source evidence</span>${j.issn.map(code=>`<span class="tag">ISSN ${escapeHtml(code)}</span>`).join("")}</div><h3>${escapeHtml(j.journal)}</h3></div><div class="score-ring" style="--score:${percent(j.score)}"><b>${percent(j.score)}</b></div></div><div class="journal-signals"><div class="signal-cell"><strong>${percent(j.topical_fit)}</strong><small>主题词汇匹配</small></div><div class="signal-cell"><strong>${j.evidence_count}</strong><small>相关论文样本</small></div><div class="signal-cell"><strong>${j.median_year || "—"}</strong><small>样本中位年份</small></div></div><ul class="reasons">${j.reasons.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul><div class="metadata">${j.evidence_dois.map(doi=>`<a href="https://doi.org/${escapeHtml(doi)}" target="_blank" rel="noopener">${escapeHtml(doi)}</a>`).join(" · ")}</div><div class="caution-strip"><strong>注意</strong><span>${escapeHtml(j.caveats.join(" "))}</span></div></article>`).join("");
}

async function submitJournals(event) {
  event.preventDefault();
  const submitBtn = event.target.querySelector("button[type='submit']") || event.submitter;
  const taskId = taskManager.start("期刊匹配中…", submitBtn);
  try { renderJournals(await api("/api/journals/match",{method:"POST",body:JSON.stringify({title:$("#journal-title").value,abstract:$("#journal-abstract").value,limit:10,papers:state.papers.slice(0,100)})})); }
  catch(error){toast(error.message,"error")} finally{taskManager.finish(taskId)}
}

function renderPolicies(policies) {
  const container = $("#policy-results");
  if (!policies.length) { container.innerHTML='<div class="empty-state"><span>∅</span><h3>没有匹配政策</h3><p>尝试更短的主题词。</p></div>'; return; }
  container.innerHTML = policies.map(p => {
    const selected = state.selectedPolicies.has(p.id);
    return `<article class="policy-card"><span class="date">${escapeHtml(p.published_at)} · OFFICIAL</span><h3>${escapeHtml(p.title)}</h3><div class="issuer">${escapeHtml(p.issuer)}</div><p>${escapeHtml(p.summary)}</p><ul>${p.signals.slice(0,4).map(s=>`<li>${escapeHtml(s)}</li>`).join("")}</ul><div class="metadata">${p.tags.slice(0,5).map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><div class="card-actions"><a href="${safeUrl(p.url)}" target="_blank" rel="noopener">核验官方原文 ↗</a><button class="text-btn" data-policy-select="${escapeHtml(p.id)}">${selected ? "✓ 已加入 Idea Lab" : "+ 加入 Idea Lab"}</button><button class="text-btn" data-policy-save="${escapeHtml(p.id)}">保存</button></div></article>`;
  }).join("");
}

async function searchPolicies(reset=false) {
  const query = reset ? "" : $("#policy-query").value.trim();
  const policyTaskId = taskManager.start("政策匹配中…");
  try { const items = await api(`/api/policies?q=${encodeURIComponent(query)}`); if(reset) $("#policy-query").value=""; renderPolicies(items); }
  catch(error){toast(error.message,"error")} finally{taskManager.finish(policyTaskId)}
}

function policyActions(event) {
  const select = event.target.closest("[data-policy-select]"); const save = event.target.closest("[data-policy-save]");
  const button = select || save; if(!button) return;
  const id = button.dataset.policySelect || button.dataset.policySave; const policy = state.policies.find(p=>p.id===id); if(!policy) return;
  if(select){if(state.selectedPolicies.has(id))state.selectedPolicies.delete(id);else state.selectedPolicies.set(id,policy);updateSelected();select.textContent=state.selectedPolicies.has(id)?"✓ 已加入 Idea Lab":"+ 加入 Idea Lab";toast(state.selectedPolicies.has(id)?"已加入 Idea Lab":"已移出 Idea Lab");}
  else saveItem("policy",id,policy.title,policy).catch(e=>toast(e.message,"error"));
}

function renderIdeas(result) {
  state.ideas = result.candidates;
  const container=$("#idea-results"); container.className="idea-results";
  container.innerHTML=result.candidates.map((idea,index)=>`<article class="idea-card"><span class="idea-number">DIRECTION 0${index+1} · ${escapeHtml(result.mode)}</span><h3>${escapeHtml(idea.title)}</h3><div class="rq"><strong>研究问题</strong><br>${escapeHtml(idea.research_question)}<br><br><strong>待证伪假设</strong><br>${escapeHtml(idea.hypothesis)}</div><div class="idea-columns"><div class="idea-block"><h4>建议方法</h4><ul>${idea.proposed_method.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div><div class="idea-block"><h4>潜在增量（待查新）</h4><ul>${idea.novelty.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div><div class="idea-block"><h4>政策连接</h4><ul>${idea.policy_alignment.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div><div class="idea-block risk-block"><h4>风险与反证</h4><ul>${idea.risks.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div><div class="idea-block"><h4>第一轮验证</h4><ul>${idea.first_validation.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div><div class="idea-block"><h4>证据锚点</h4><ul>${idea.evidence.map(x=>`<li>${escapeHtml(x)}</li>`).join("")}</ul></div></div><div class="card-actions"><button class="text-btn" data-idea-save="${index}">保存这个 Idea</button></div></article>`).join("")+`<div class="source-note"><strong>研究诚信提示</strong><p>${escapeHtml(result.warnings.join(" "))}</p></div>`;
}

function renderIdeaDocuments() {
  const container = $("#idea-document-list");
  if (!state.ideaDocuments.length) {
    container.innerHTML = "";
    return;
  }
  const total = state.ideaDocuments.reduce((sum, item) => sum + Number(item.char_count || 0), 0);
  container.innerHTML = `<div class="document-list-head"><span>已解析 ${state.ideaDocuments.length} 份材料</span><small>${total.toLocaleString()} 字符将与手动说明合并</small></div>${state.ideaDocuments.map(item => `
    <article class="idea-document-card">
      <span class="document-format">${escapeHtml(item.format)}</span>
      <div class="document-copy"><strong>${escapeHtml(item.filename)}</strong><p>${Number(item.char_count || 0).toLocaleString()} 字符${item.truncated ? " · 已按安全上限截取" : " · 解析完成"}</p>
        <details><summary>查看解析预览</summary><pre>${escapeHtml(truncate(item.text, 900))}</pre></details>
        ${(item.warnings || []).map(warning => `<small class="document-warning">${escapeHtml(warning)}</small>`).join("")}
      </div>
      <button class="document-remove" type="button" data-document-remove="${escapeHtml(item.id)}" aria-label="移除 ${escapeHtml(item.filename)}">×</button>
    </article>`).join("")}`;
}

async function importIdeaDocuments(fileList) {
  const remaining = 5 - state.ideaDocuments.length;
  if (remaining <= 0) return toast("每次最多导入 5 份材料，请先移除一份", "error");
  const files = [...fileList].slice(0, remaining);
  if (!files.length) return;
  if (fileList.length > remaining) toast(`本次只导入前 ${remaining} 份材料`, "error");
  const importDocsTaskId = taskManager.start(`解析 ${files.length} 份材料…`);
  let completed = 0;
  try {
    for (const file of files) {
      if (file.size > 12 * 1024 * 1024) {
        toast(`${file.name} 超过 12 MB，已跳过`, "error");
        continue;
      }
      const form = new FormData();
      form.append("file", file);
      try {
        const response = await fetch("/api/ideas/import", {method: "POST", body: form});
        let payload = {};
        try { payload = await response.json(); } catch {}
        if (!response.ok) throw new Error(payload.detail || `${file.name} 解析失败`);
        state.ideaDocuments.push({...payload, id: `${Date.now()}-${Math.random().toString(16).slice(2)}`});
        completed += 1;
        renderIdeaDocuments();
      } catch (error) {
        toast(`${file.name}：${error.message}`, "error");
      }
    }
    if (completed) toast(`已解析 ${completed} 份材料，生成时将自动合并`);
  } finally {
    $("#idea-work-files").value = "";
    taskManager.finish(importDocsTaskId);
  }
}

function combinedExistingWork() {
  const sections = [];
  const manual = $("#existing-work").value.trim();
  if (manual) sections.push(`【用户补充说明】\n${manual}`);
  state.ideaDocuments.forEach(item => sections.push(`【导入材料：${item.filename}】\n${item.text}`));
  const combined = sections.join("\n\n");
  return {text: combined.slice(0, 30000), truncated: combined.length > 30000};
}

async function submitIdeas(event) {
  event.preventDefault(); const existing=combinedExistingWork(); if(existing.text.length<20)return toast("请手动说明已有工作，或上传至少一份可解析材料","error");
  if(existing.truncated)toast("合并后内容较长，本次已按 30,000 字符上限提交；建议移除关联度较低的材料", "error");
  const body={existing_work:existing.text,research_goal:$("#research-goal").value,keywords:$("#idea-keywords").value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),papers:[...state.selectedPapers.values()],policy_ids:[...state.selectedPolicies.keys()],use_llm:$("#idea-use-llm").checked};
  const ideaBtn = event.target.querySelector("button[type='submit']") || event.submitter;
  const ideaTaskId = taskManager.start("Idea生成中…", ideaBtn);
  try{renderIdeas(await api("/api/ideas",{method:"POST",body:JSON.stringify(body)}))}catch(error){toast(error.message,"error")}finally{taskManager.finish(ideaTaskId)}
}

function usageLine(usage = {}) {
  const input = Number(usage.input_tokens || 0).toLocaleString();
  const output = Number(usage.output_tokens || 0).toLocaleString();
  const cache = Number(usage.cache_hit_tokens || 0).toLocaleString();
  const cacheRate = usage.cache_hit_rate != null ? ` (${Math.round(usage.cache_hit_rate * 100)}%)` : "";
  const provider = usage.provider ? `${escapeHtml(usage.provider)} / ` : "";
  const fallback = usage.fallback_used ? " · 已使用备用路由" : "";
  const checked = usage.quality_status === "passed" ? " · 质量门已通过" : "";
  return `${provider}${escapeHtml(usage.model || "模型")} · 输入 ${input} · 输出 ${output} · 缓存 ${cache}${cacheRate}${fallback}${checked}`;
}

async function generateSearchStrategy() {
  const query = $("#search-query").value.trim();
  if (query.length < 2) return toast("请先填写中文研究主题", "error");
  const button = $("#generate-search-strategy");
  const strategyTaskId = taskManager.start("检索策略生成中…", button);
  try {
    const result = await api("/api/search/strategy", {method:"POST", body:JSON.stringify({
      query,
      field: $("#search-field-hint").value.trim(),
      project_id: Number($("#search-project").value) || null,
    })});
    $("#search-query").value = result.chinese_query;
    $("#search-query-en").value = result.english_query;
    const container = $("#search-strategy-result");
    container.className = "strategy-result";
    container.innerHTML = `<div class="strategy-head"><div><span class="eyebrow">双语检索策略已生成</span><h3>可以继续编辑，再开始检索</h3></div><small>${usageLine(result.usage)}</small></div><div class="strategy-columns"><div><strong>中文概念</strong><p>${result.chinese_keywords.map(value=>`<span>${escapeHtml(value)}</span>`).join("") || "未返回"}</p></div><div><strong>英文术语</strong><p>${result.english_keywords.map(value=>`<span>${escapeHtml(value)}</span>`).join("")}</p></div></div>${result.exclusions.length ? `<p class="strategy-exclusions"><b>建议排除：</b>${result.exclusions.map(escapeHtml).join("；")}</p>` : ""}${result.explanation.length ? `<ul>${result.explanation.map(value=>`<li>${escapeHtml(value)}</li>`).join("")}</ul>` : ""}`;
    toast("双语检索式已写入输入框，可人工调整");
    loadModelStatus(false);
  } catch (error) {
    toast(error.message, "error");
    if (error.status === 409) go("models");
  } finally { taskManager.finish(strategyTaskId); }
}

function renderDiscussionProject() {
  const project = currentProject();
  const name = $("#discussion-project-name");
  if (!name) return;
  name.textContent = project?.name || "尚未选择";
  $("#discussion-project-question").textContent = project?.research_question || "请先建立或选择一个科研项目。";
  const submit = $("#discussion-form button[type='submit']");
  if (submit) submit.disabled = !project;
}

function renderDiscussion(result) {
  state.lastDiscussion = result;
  const container = $("#discussion-results");
  container.className = "discussion-results panel";
  const refs = result.evidence_refs.length ? result.evidence_refs.map(ref=>`<span>${escapeHtml(ref)}</span>`).join("") : '<em>当前回答未引用项目证据，请将结论视为待核验建议。</em>';
  container.innerHTML = `<div class="discussion-answer-head"><span class="eyebrow">直接结论</span><small>${usageLine(result.usage)}</small></div><h2>${escapeHtml(result.answer)}</h2><div class="discussion-points">${result.points.map((point,index)=>`<article><b>${String(index+1).padStart(2,"0")}</b><div><h3>${escapeHtml(point.title)}</h3><p>${escapeHtml(point.detail)}</p></div></article>`).join("")}</div><section class="discussion-evidence"><strong>本次引用的项目证据</strong><div>${refs}</div></section><div class="discussion-lower"><section><span class="eyebrow">仍不确定</span><ul>${result.uncertainties.map(value=>`<li>${escapeHtml(value)}</li>`).join("") || "<li>模型未明确列出，请主动检查证据边界。</li>"}</ul></section><section><span class="eyebrow">本周可交付行动</span><ol>${result.next_actions.map(value=>`<li>${escapeHtml(value)}</li>`).join("")}</ol></section></div><div class="card-actions"><button class="text-btn" type="button" id="save-discussion">保存到当前课题证据库</button><button class="text-btn" type="button" id="copy-discussion">复制研讨结论</button></div>`;
}

async function submitDiscussion(event) {
  event.preventDefault();
  const project = currentProject();
  if (!project) return toast("请先建立或选择科研项目", "error");
  const discussBtn = event.target.querySelector("button[type='submit']") || event.submitter;
  const discussTaskId = taskManager.start("课题研讨中…", discussBtn);
  try {
    const result = await api("/api/discussions", {method:"POST", body:JSON.stringify({
      project_id: project.id,
      question: $("#discussion-question").value.trim(),
      mode: $("#discussion-mode").value,
      include_evidence: $("#discussion-evidence").checked,
      include_policies: $("#discussion-policies").checked,
      policy_ids: [...state.selectedPolicies.keys()],
    })});
    renderDiscussion(result);
    loadModelStatus(false);
  } catch (error) {
    toast(error.message, "error");
    if (error.status === 409) go("models");
  } finally { taskManager.finish(discussTaskId); }
}

function renderModelStatus(status) {
  if (!status || !$("#model-status-title")) return;
  state.llmStatus = status;
  const ready = status.enabled && status.api_key_configured;
  const count = Number(status.active_count || 0);
  const title = ready ? `${count} 个模型服务已进入科研工作流` : "连接第一个模型，解锁深度科研任务";
  $("#model-status-title").textContent = title;
  $("#model-status-description").textContent = ready
    ? "路由器会按任务选择快速或深度模型。任何生成结论都要经过中文结构、证据编号与结果边界检查。"
    : "选择你已有账户的服务商，输入 Key 并测试连接。密钥在服务端加密，网页不会再次取得明文。";
  $("#model-status-hero").classList.toggle("ready", ready);
  if ($("#model-health-count")) $("#model-health-count").textContent = count;
  $("#model-status-pills").innerHTML = [
    ["连接服务", `${count} / ${(status.providers || []).length}`],
    ["凭据保护", status.security?.encrypted_at_rest ? "已加密" : "环境变量"],
    ["任务策略", ({economy:"节省",balanced:"均衡",quality:"质量"})[status.routing] || status.routing || "单模型"],
    ["故障切换", status.routing_settings?.fallback_enabled ? "已开启" : "已关闭"],
  ].map(([label,value])=>`<span><small>${escapeHtml(label)}</small><b>${escapeHtml(value)}</b></span>`).join("");
  $("#model-route-grid").innerHTML = (status.task_routes || []).map((route,index)=>`<article class="model-route-card"><span>${String(index+1).padStart(2,"0")}</span><div><small>${escapeHtml(route.quality_gate || "结构校验")}</small><h3>${escapeHtml(route.task)}</h3><p>${escapeHtml(route.model || "配置模型后启用")}</p></div></article>`).join("");
  renderProviderGrid(status.providers || []);
  renderRoutingControls(status);
  const usage = status.usage || {};
  const metrics = [["调用次数", usage.calls || 0],["输入 Token", usage.input_tokens || 0],["输出 Token", usage.output_tokens || 0],["缓存命中", usage.cache_hit_tokens || 0],["推理 Token", usage.reasoning_tokens || 0],["平均耗时", `${usage.average_latency_ms || 0} ms`]];
  $("#model-usage-grid").innerHTML = metrics.map(([label,value])=>`<article class="usage-card"><span>${escapeHtml(label)}</span><strong>${typeof value === "number" ? value.toLocaleString() : escapeHtml(value)}</strong><small>近 ${usage.days || 30} 天</small></article>`).join("");
  const runs = usage.recent || [];
  const runList = $("#model-run-list");
  if (!runs.length) { runList.className = "model-run-list empty-state"; runList.innerHTML = '<span>⌁</span><p>还没有模型调用记录。</p>'; }
  else { runList.className = "model-run-list"; runList.innerHTML = runs.map(run=>`<article><div><strong>${escapeHtml(run.task)}</strong><span>${escapeHtml(run.model)}</span></div><p>输入 ${Number(run.input_tokens).toLocaleString()} · 输出 ${Number(run.output_tokens).toLocaleString()} · 缓存 ${Number(run.cache_hit_tokens).toLocaleString()} · ${Number(run.latency_ms).toLocaleString()} ms</p><time>${escapeHtml(new Date(run.created_at).toLocaleString())}</time></article>`).join(""); }
}

function renderRoutingControls(status) {
  const routing = status.routing_settings || {mode:"balanced",primary_provider:"",fallback_enabled:true};
  $("#model-routing-mode").value = routing.mode || "balanced";
  $("#model-fallback-enabled").checked = routing.fallback_enabled !== false;
  const configured = (status.providers || []).filter(provider=>provider.configured);
  $("#model-primary-provider").innerHTML = '<option value="">按优先级自动选择</option>' + configured.map(provider=>`<option value="${escapeHtml(provider.id)}">${escapeHtml(provider.name)}</option>`).join("");
  $("#model-primary-provider").value = routing.primary_provider || "";
}

function renderProviderGrid(providers) {
  const visible = providers.filter(provider=>state.providerRegion === "all" || provider.region === state.providerRegion);
  const container = $("#provider-grid");
  container.innerHTML = visible.map(provider=>{
    const statusText = provider.enabled ? "已连接" : provider.configured ? "已停用" : "未配置";
    const models = provider.fast_model === provider.quality_model ? provider.fast_model : `${provider.fast_model} / ${provider.quality_model}`;
    return `<article class="provider-card ${provider.enabled ? "connected" : ""}">
      <div class="provider-card-head"><div class="provider-monogram">${escapeHtml(provider.name.slice(0,2))}</div><div><small>${escapeHtml(provider.region)} · ${escapeHtml(provider.protocol.replaceAll("_"," "))}</small><h3>${escapeHtml(provider.name)}</h3></div><span class="provider-state">${statusText}</span></div>
      <p>${escapeHtml(provider.description)}</p>
      <div class="provider-model"><span>当前模型</span><strong>${escapeHtml(models)}</strong></div>
      ${provider.notice ? `<small class="provider-card-notice">${escapeHtml(provider.notice)}</small>` : ""}
      <div class="provider-card-actions"><button class="text-btn" data-provider-config="${escapeHtml(provider.id)}">${provider.configured ? "管理配置" : "连接服务"}</button>${provider.enabled ? `<button class="text-btn" data-provider-test="${escapeHtml(provider.id)}">测试</button>` : ""}<a href="${safeUrl(provider.docs_url)}" target="_blank" rel="noopener">官方文档 ↗</a></div>
    </article>`;
  }).join("") || '<div class="empty-state provider-empty"><span>⌁</span><p>这个分组暂时没有服务商。</p></div>';
}

function providerById(id) { return (state.llmStatus?.providers || []).find(provider=>provider.id === id); }

function openProviderDialog(id) {
  const provider = providerById(id);
  if (!provider) return;
  $("#provider-id").value = provider.id;
  $("#provider-dialog-region").textContent = `${provider.region} · ${provider.protocol.replaceAll("_"," ")}`;
  $("#provider-dialog-title").textContent = provider.name;
  $("#provider-dialog-description").textContent = provider.description;
  $("#provider-api-key").value = "";
  $("#provider-api-key").placeholder = provider.configured ? `已保存 ${provider.key_hint}；留空不修改` : "粘贴 API Key";
  $("#provider-base-url").value = provider.base_url;
  $("#provider-base-url").readOnly = !provider.base_url_editable;
  $("#provider-fast-model").value = provider.fast_model;
  $("#provider-quality-model").value = provider.quality_model;
  $("#provider-consent").checked = false;
  $("#provider-notice").textContent = provider.notice || "模型名称会变化；若测试提示模型不可用，请按官方控制台修改模型 ID。";
  $("#delete-provider").classList.toggle("hidden", !provider.configured);
  $("#provider-dialog").showModal();
}

async function saveProvider(event) {
  event.preventDefault();
  const id = $("#provider-id").value;
  if (!$("#provider-consent").checked) return toast("请先确认数据发送与费用边界", "error");
  const button = $("#save-provider");
  button.disabled = true;
  try {
    await api(`/api/model-providers/${encodeURIComponent(id)}`, {method:"PUT", body:JSON.stringify({
      api_key: $("#provider-api-key").value,
      base_url: $("#provider-base-url").value,
      fast_model: $("#provider-fast-model").value,
      quality_model: $("#provider-quality-model").value,
      enabled: true,
    })});
    $("#provider-dialog").close();
    toast("配置已加密保存；建议立即执行连接测试");
    await loadModelStatus();
  } catch (error) { toast(error.message, "error"); }
  finally { button.disabled = false; }
}

async function testProvider(id) {
  const testTaskId = taskManager.start(`测试 ${providerById(id)?.name || "模型服务"}…`);
  try {
    const result = await api(`/api/model-providers/${encodeURIComponent(id)}/test`, {method:"POST", body:"{}"});
    toast(result.ok ? "连接与结构化输出测试通过" : "服务已响应，但结构化结果未通过", result.ok ? "ok" : "error");
    await loadModelStatus(false);
  } catch (error) { toast(error.message, "error"); }
  finally { taskManager.finish(testTaskId); }
}

async function deleteProvider() {
  const id = $("#provider-id").value;
  const provider = providerById(id);
  if (!window.confirm(`删除 ${provider?.name || "该服务"} 的密钥与路由配置？`)) return;
  try {
    await api(`/api/model-providers/${encodeURIComponent(id)}`, {method:"DELETE"});
    $("#provider-dialog").close();
    toast("模型配置已删除");
    await loadModelStatus();
  } catch (error) { toast(error.message, "error"); }
}

async function saveModelRouting(event) {
  event.preventDefault();
  try {
    await api("/api/model-routing", {method:"PUT", body:JSON.stringify({
      mode: $("#model-routing-mode").value,
      primary_provider: $("#model-primary-provider").value,
      fallback_enabled: $("#model-fallback-enabled").checked,
    })});
    toast("任务路由已更新");
    await loadModelStatus();
  } catch (error) { toast(error.message, "error"); }
}

async function loadModelStatus(showErrors = true) {
  try { renderModelStatus(await api("/api/llm/status")); }
  catch (error) { if (showErrors) toast(error.message, "error"); }
}

async function testModelConnection() {
  const button = $("#test-llm");
  const quickTestTaskId = taskManager.start("模型连接测试…", button);
  try { const result = await api("/api/llm/test", {method:"POST", body:"{}"}); toast(result.ok ? "主路由连接与结构化输出测试通过" : "模型已响应，但返回内容不符合测试约定", result.ok ? "ok" : "error"); await loadModelStatus(); }
  catch (error) { toast(error.message, "error"); }
  finally { taskManager.finish(quickTestTaskId); }
}

async function loadLibrary(kind="") {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  const projectId = Number($("#library-project")?.value) || null;
  if (projectId) params.set("project_id", String(projectId));
  try { state.library=await api(`/api/library${params.size ? `?${params}` : ""}`); renderLibrary(state.library); }
  catch(error){toast(error.message,"error")}
}

function renderLibrary(items) {
  const container=$("#library-results"); if(!items.length){container.className="result-list empty-state";container.innerHTML='<span>▣</span><h3>这里还没有证据</h3><p>从论文、政策、分析、Idea 或科研研讨室保存内容。</p>';return}
  container.className="result-list";container.innerHTML=items.map(item=>{const project=state.projects.find(p=>p.id===item.project_id);return `<article class="library-card"><span class="kind-label">${escapeHtml(item.kind.toUpperCase())}</span><div><h3>${escapeHtml(item.title)}</h3><small>${escapeHtml(new Date(item.created_at).toLocaleString())} · ${project ? `项目：${escapeHtml(project.name)} · ` : "未归类 · "}${escapeHtml(item.external_id)}</small>${item.note ? `<p class="abstract" style="margin-top:6px;font-style:italic;color:var(--violet)">📝 ${escapeHtml(truncate(item.note, 120))}</p>` : ""}</div><div style="display:flex;gap:6px;align-items:center"><button class="note-toggle" data-library-note="${item.id}" title="添加/编辑笔记">📝</button><button class="text-btn danger" data-library-delete="${item.id}">删除</button></div></article><div class="note-panel" id="note-panel-${item.id}"><textarea placeholder="写下你对这篇文献的理解、疑问或灵感…" data-note-text="${item.id}">${escapeHtml(item.note || "")}</textarea><button class="btn btn-secondary" style="margin-top:6px" data-note-save="${item.id}">保存笔记</button></div>`}).join("");
}

async function saveLibraryNote(id, note) {
  try {
    await api(`/api/library/${id}`, {method:"PATCH", body:JSON.stringify({note})});
    toast("笔记已保存");
  } catch(e) { toast(e.message, "error"); }
}

async function deleteLibrary(id){if(!window.confirm("从本地证据库删除这条记录？"))return;try{await api(`/api/library/${id}`,{method:"DELETE"});toast("已删除");await loadLibrary($(".library-filters button.active").dataset.kind);if(state.activeProjectId)await loadProjectWorkspace()}catch(e){toast(e.message,"error")}}

function downloadText(content, filename, type) {
  const blob = new Blob([content], {type});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function exportBibliography(format) {
  if (!state.papers.length) return toast("请先检索或导入论文题录", "error");
  try {
    const content = await api("/api/export/bibliography", {method:"POST", body:JSON.stringify({format, papers:state.papers.slice(0, 200)})});
    downloadText(content, format === "ris" ? "latticescholar-evidence.ris" : "latticescholar-evidence.bib", "text/plain;charset=utf-8");
    toast(`已导出 ${state.papers.length} 条 ${format === "ris" ? "RIS" : "BibTeX"} 题录`);
  } catch (error) { toast(error.message, "error"); }
}

async function exportBrief(){
  const exportTaskId = taskManager.start("简报导出中…");try{const policies=[...state.selectedPolicies.values()];const papers=[...state.selectedPapers.values()];const content=await api("/api/export",{method:"POST",body:JSON.stringify({title:currentProject()?.name || "LatticeScholar Research Brief",query:$("#search-query").value,papers,analyses:state.analyses.slice(0,5),ideas:state.ideas,policies})});downloadText(content,"latticescholar-research-brief.md","text/markdown;charset=utf-8");toast("研究简报已导出")}catch(e){toast(e.message,"error")}finally{taskManager.finish(exportTaskId)}
}

function loadStudentTasks() {
  try { state.studentTasks = JSON.parse(localStorage.getItem("latticescholar-student-tasks") || "[]"); }
  catch { state.studentTasks = []; }
  if (!Array.isArray(state.studentTasks)) state.studentTasks = [];
}

function saveStudentTasks() {
  localStorage.setItem("latticescholar-student-tasks", JSON.stringify(state.studentTasks));
  renderStudentTasks();
}

function renderStudentTasks() {
  loadStudentTasks();
  const container = $("#student-task-list");
  if (!container) return;
  const completed = state.studentTasks.filter(task=>task.done).length;
  $("#student-task-progress").textContent = `${completed} / ${state.studentTasks.length}`;
  if (!state.studentTasks.length) {
    container.className = "student-task-list empty-state";
    container.innerHTML = '<span>✓</span><h3>还没有任务</h3><p>从一个 30–90 分钟能完成的交付物开始。</p>';
    return;
  }
  container.className = "student-task-list";
  container.innerHTML = state.studentTasks.map(task=>{
    const overdue = task.date && !task.done && new Date(`${task.date}T23:59:59`) < new Date();
    return `<article class="student-task ${task.done ? "done" : ""}"><button type="button" data-task-toggle="${escapeHtml(task.id)}" aria-label="切换完成状态">${task.done ? "✓" : ""}</button><div><div class="metadata"><span class="tag">${escapeHtml(task.stage)}</span>${task.date ? `<span class="tag ${overdue ? "overdue" : ""}">${overdue ? "已逾期 · " : ""}${escapeHtml(task.date)}</span>` : ""}</div><strong>${escapeHtml(task.title)}</strong>${task.proof ? `<p>完成标准：${escapeHtml(task.proof)}</p>` : ""}</div><button class="text-btn danger" type="button" data-task-delete="${escapeHtml(task.id)}">删除</button></article>`;
  }).join("");
}

function submitStudentTask(event) {
  event.preventDefault();
  loadStudentTasks();
  state.studentTasks.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title: $("#student-task-title").value.trim(),
    stage: $("#student-task-stage").value,
    date: $("#student-task-date").value,
    proof: $("#student-task-proof").value.trim(),
    done: false,
  });
  event.target.reset();
  saveStudentTasks();
  toast("任务已加入本周计划");
}

function studentTaskAction(event) {
  const toggle = event.target.closest("[data-task-toggle]");
  const remove = event.target.closest("[data-task-delete]");
  if (!toggle && !remove) return;
  loadStudentTasks();
  const id = (toggle || remove).dataset.taskToggle || (toggle || remove).dataset.taskDelete;
  if (toggle) state.studentTasks = state.studentTasks.map(task=>task.id === id ? {...task, done:!task.done} : task);
  if (remove) state.studentTasks = state.studentTasks.filter(task=>task.id !== id);
  saveStudentTasks();
}

document.addEventListener("DOMContentLoaded",()=>{
  initialize();
  $("#email-login-form").addEventListener("submit", emailLogin);
  $("#shared-login-form").addEventListener("submit", sharedLogin);
  $("#change-email").addEventListener("click", resetEmailLogin);
  $$("[data-page]").forEach(b=>b.addEventListener("click",()=>go(b.dataset.page)));
  $$("[data-go]").forEach(b=>b.addEventListener("click",()=>go(b.dataset.go)));
  $("#project-form").addEventListener("submit",createProject);
  $("#project-list").addEventListener("click",projectActions);
  $("#project-detail").addEventListener("click",projectActions);
  $("#project-history").addEventListener("click",historyActions);
  $("#search-form").addEventListener("submit",submitSearch);$("#search-results").addEventListener("click",setupPaperActions);
  $("#generate-search-strategy").addEventListener("click",generateSearchStrategy);
  $("#search-project").addEventListener("change",event=>{if(event.target.value)setActiveProject(event.target.value,false)});
  $("#search-sort").addEventListener("change",rerenderSortedPapers);
  $("#paper-tabs").addEventListener("click",event=>{
    const button = event.target.closest("[data-paper-filter]");
    if (!button || !state.lastSearchResponse) return;
    state.paperFilter = button.dataset.paperFilter;
    $$("#paper-tabs button").forEach(item=>item.classList.toggle("active", item === button));
    renderPapers(state.lastSearchResponse);
  });
  $("#export-bibtex").addEventListener("click",()=>exportBibliography("bibtex"));
  $("#export-ris").addEventListener("click",()=>exportBibliography("ris"));
  $("#import-form").addEventListener("submit",importBibliography);
  $("#search-query").addEventListener("change",()=>renderConnectors(state.connectors));
  $("#analyze-form").addEventListener("submit",submitAnalysis);
  $("#pdf-file").addEventListener("change",renderPdfSelection);
  $$('[data-analysis-focus]').forEach(button=>button.addEventListener("click",()=>{
    $("#analysis-question").value = button.dataset.analysisFocus;
    $$('[data-analysis-focus]').forEach(item=>item.classList.toggle("active",item===button));
  }));
  $$('[data-analyze-mode]').forEach(b=>b.addEventListener("click",()=>{state.analyzeMode=b.dataset.analyzeMode;$$('[data-analyze-mode]').forEach(x=>x.classList.toggle("active",x===b));$("#analyze-text-fields").classList.toggle("hidden",state.analyzeMode!=="text");$("#analyze-pdf-fields").classList.toggle("hidden",state.analyzeMode!=="pdf")}));
  $("#journal-form").addEventListener("submit",submitJournals);
  $("#policy-search-btn").addEventListener("click",()=>searchPolicies(false));$("#policy-reset-btn").addEventListener("click",()=>searchPolicies(true));$("#policy-results").addEventListener("click",policyActions);
  $("#idea-form").addEventListener("submit",submitIdeas);$("#idea-results").addEventListener("click",e=>{const b=e.target.closest("[data-idea-save]");if(b){const idea=state.ideas[Number(b.dataset.ideaSave)];saveItem("idea",`idea-${Date.now()}-${b.dataset.ideaSave}`,idea.title,idea).catch(x=>toast(x.message,"error"))}});
  $("#choose-work-files").addEventListener("click",()=>$("#idea-work-files").click());
  $("#idea-work-files").addEventListener("change",event=>importIdeaDocuments(event.target.files));
  const workDropzone=$("#work-dropzone");
  workDropzone.addEventListener("click",event=>{if(!event.target.closest("button"))$("#idea-work-files").click()});
  workDropzone.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();$("#idea-work-files").click()}});
  ["dragenter","dragover"].forEach(name=>workDropzone.addEventListener(name,event=>{event.preventDefault();workDropzone.classList.add("is-dragging")}));
  ["dragleave","drop"].forEach(name=>workDropzone.addEventListener(name,event=>{event.preventDefault();workDropzone.classList.remove("is-dragging")}));
  workDropzone.addEventListener("drop",event=>importIdeaDocuments(event.dataTransfer.files));
  $("#idea-document-list").addEventListener("click",event=>{const button=event.target.closest("[data-document-remove]");if(!button)return;state.ideaDocuments=state.ideaDocuments.filter(item=>item.id!==button.dataset.documentRemove);renderIdeaDocuments();toast("已移除这份材料")});
  $("#discussion-form").addEventListener("submit",submitDiscussion);
  $("#discussion-form").addEventListener("click",event=>{const prompt=event.target.closest("[data-discussion-prompt]");if(prompt)$("#discussion-question").value=prompt.dataset.discussionPrompt});
  $("#discussion-results").addEventListener("click",event=>{
    if(event.target.closest("#save-discussion") && state.lastDiscussion){const project=currentProject();saveItem("discussion",`discussion-${Date.now()}`,`课题研讨：${truncate($("#discussion-question").value.trim(),60)}`,{question:$("#discussion-question").value.trim(),mode:$("#discussion-mode").value,project:project?.name,result:state.lastDiscussion}).catch(error=>toast(error.message,"error"))}
    if(event.target.closest("#copy-discussion") && state.lastDiscussion){const text=[state.lastDiscussion.answer,...state.lastDiscussion.points.map(point=>`${point.title}：${point.detail}`),"下一步：",...state.lastDiscussion.next_actions].join("\n");navigator.clipboard.writeText(text).then(()=>toast("研讨结论已复制")).catch(()=>toast("复制失败，请手动选择文本","error"))}
  });
  $("#library-results").addEventListener("click",e=>{
    const b=e.target.closest("[data-library-delete]");if(b)deleteLibrary(b.dataset.libraryDelete);
    const noteBtn=e.target.closest("[data-library-note]");if(noteBtn){const panel=document.getElementById(`note-panel-${noteBtn.dataset.libraryNote}`);if(panel)panel.classList.toggle("open")}
    const saveBtn=e.target.closest("[data-note-save]");if(saveBtn){const id=saveBtn.dataset.noteSave;const textarea=document.querySelector(`[data-note-text="${id}"]`);if(textarea)saveLibraryNote(id,textarea.value)}
  });$$('.library-filters button').forEach(b=>b.addEventListener("click",()=>{$$('.library-filters button').forEach(x=>x.classList.toggle("active",x===b));loadLibrary(b.dataset.kind)}));
  $("#library-project").addEventListener("change",()=>loadLibrary($(".library-filters button.active").dataset.kind));
  $("#export-library").addEventListener("click",exportBrief);
  $("#logout-button").addEventListener("click",logout);
  $("#policy-sync-button").addEventListener("click",syncPolicies);
  $("#policy-candidate-list").addEventListener("click",reviewPolicyCandidate);
  $("#student-task-form").addEventListener("submit",submitStudentTask);
  $("#student-task-list").addEventListener("click",studentTaskAction);
  $("#student-clear-completed").addEventListener("click",()=>{loadStudentTasks();state.studentTasks=state.studentTasks.filter(task=>!task.done);saveStudentTasks();});
  $("#test-llm").addEventListener("click",testModelConnection);
  $("#model-routing-form").addEventListener("submit", saveModelRouting);
  $("#provider-form").addEventListener("submit", saveProvider);
  $("#provider-dialog-close").addEventListener("click",()=>$("#provider-dialog").close());
  $("#provider-dialog-cancel").addEventListener("click",()=>$("#provider-dialog").close());
  $("#toggle-provider-key").addEventListener("click",()=>{const input=$("#provider-api-key");input.type=input.type === "password" ? "text" : "password";$("#toggle-provider-key").textContent=input.type === "password" ? "显示" : "隐藏";});
  $("#delete-provider").addEventListener("click", deleteProvider);
  $("#provider-grid").addEventListener("click",event=>{const config=event.target.closest("[data-provider-config]");const test=event.target.closest("[data-provider-test]");if(config)openProviderDialog(config.dataset.providerConfig);if(test)testProvider(test.dataset.providerTest);});
  $$("[data-provider-region]").forEach(button=>button.addEventListener("click",()=>{state.providerRegion=button.dataset.providerRegion;$$('[data-provider-region]').forEach(item=>item.classList.toggle("active",item===button));renderProviderGrid(state.llmStatus?.providers || []);}));
  renderStudentTasks();

  // Dark mode toggle
  initTheme();
  $("#theme-toggle").addEventListener("click", toggleTheme);

  // Back to top
  const backToTop = $("#back-to-top");
  window.addEventListener("scroll", () => {
    backToTop.classList.toggle("visible", window.scrollY > 400);
  }, {passive: true});
  backToTop.addEventListener("click", () => window.scrollTo({top: 0, behavior: "smooth"}));

  // Keyboard shortcuts
  document.addEventListener("keydown", handleShortcuts);
});

// === Theme Management ===
function initTheme() {
  const saved = localStorage.getItem("latticescholar-theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = saved || (prefersDark ? "dark" : "light");
  applyTheme(theme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("latticescholar-theme", theme);
  const icon = theme === "dark" ? "☾" : "☀";
  const toggle = $("#theme-toggle");
  if (toggle) toggle.textContent = icon;
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  applyTheme(current === "dark" ? "light" : "dark");
}

// === Keyboard Shortcuts ===
function handleShortcuts(event) {
  if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA" || event.target.tagName === "SELECT") {
    if (event.key === "Escape") event.target.blur();
    return;
  }

  const pages = ["overview", "projects", "explore", "analyze", "journals", "policies", "ideas"];

  if (event.ctrlKey || event.metaKey) {
    if (event.key === "d" || event.key === "D") { event.preventDefault(); toggleTheme(); return; }
    const num = parseInt(event.key);
    if (num >= 1 && num <= 7) { event.preventDefault(); go(pages[num - 1]); return; }
  }

  if (event.key === "/") { event.preventDefault(); const q = $("#search-query"); if (q) { go("explore"); q.focus(); } return; }
  if (event.key === "?") { event.preventDefault(); const hint = $("#shortcut-hint"); hint.classList.toggle("visible"); setTimeout(() => hint.classList.remove("visible"), 5000); return; }
}

// === Progress Bar ===
function showProgress(percent = 0) {
  const bar = $("#progress-bar");
  const inner = $("#progress-inner");
  if (!bar || !inner) return;
  bar.classList.add("active");
  inner.style.width = `${Math.min(percent, 95)}%`;
}

function hideProgress() {
  const bar = $("#progress-bar");
  const inner = $("#progress-inner");
  if (!bar || !inner) return;
  inner.style.width = "100%";
  setTimeout(() => { bar.classList.remove("active"); inner.style.width = "0"; }, 300);
}
