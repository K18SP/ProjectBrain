const state = {
  project: localStorage.getItem('projectbrain-project') || '',
  projects: [],
  loading: 0,
  asking: false,
  graph: null,
  lastInvestigation: null,
  session: sessionStorage.getItem('projectbrain-session') || crypto.randomUUID(),
};
sessionStorage.setItem('projectbrain-session', state.session);

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]));
const recordIcon = { Project: '▣', Milestone: '◇', Task: '☑', PullRequest: '⌘', Person: '◉', Team: '◉', Service: '⬡', Decision: '✦', Document: '▤', DocumentSection: '▤', Investigation: '◷', Repository: '⌘' };

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({ detail: 'The server could not complete the request. Please try again.' }));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((item) => item.msg).join('; ') : data.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

function toast(message) {
  const element = $('toast');
  element.textContent = message;
  element.classList.add('visible');
  clearTimeout(window.projectBrainToast);
  window.projectBrainToast = setTimeout(() => element.classList.remove('visible'), 4200);
}

function showView(name) {
  document.querySelectorAll('.view').forEach((element) => element.classList.toggle('active', element.id === `view-${name}`));
  document.querySelectorAll('.nav-item').forEach((element) => element.classList.toggle('active', element.dataset.view === name));
  if (name === 'graph') renderRecords();
  if (name === 'activity') renderHistory();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setConnectionStatus(connected) {
  $('db-status').textContent = connected ? 'Project data connected' : 'Project data unavailable';
  $('status-dot').className = `status-dot ${connected ? 'ready' : 'error'}`;
  $('connection-notice').hidden = connected;
  if (!connected) $('project-select').innerHTML = '<option value="">No project connected</option>';
}

async function loadProjects() {
  try {
    const health = await api('/api/health');
    setConnectionStatus(health.graph === 'connected');
    if (health.graph !== 'connected') return;

    const projects = await api('/api/projects');
    state.projects = projects;
    $('empty-workspace').hidden = projects.length > 0;
    $('import-destination').innerHTML = '<option value="">Create a project from this source</option>' + projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');

    const selector = $('project-select');
    selector.innerHTML = projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    if (!projects.length) {
      state.project = '';
      state.graph = null;
      selector.innerHTML = '<option value="">Add your first project</option>';
      return;
    }
    if (!projects.some((project) => project.id === state.project)) state.project = projects[0].id;
    selector.value = state.project;
    localStorage.setItem('projectbrain-project', state.project);
    await loadGraph();
  } catch (error) {
    setConnectionStatus(false);
    toast(error.message);
  }
}

async function loadGraph() {
  const version = ++state.loading;
  const project = state.project;
  if (!project) return;
  try {
    const graph = await api(`/api/projects/${encodeURIComponent(project)}/graph`);
    if (version !== state.loading || project !== state.project) return;
    state.graph = graph;
    renderHome();
    renderRecords();
    renderHistory();
  } catch (error) {
    toast(error.message);
  }
}

function renderHome() {
  if (!state.graph) return;
  const { project, nodes, investigations } = state.graph;
  $('project-name').textContent = project.name;
  $('metric-nodes').textContent = nodes.length;
  $('metric-investigations').textContent = investigations.length;
  $('project-description').textContent = project.description || 'Work connected to this project.';
  const questions = projectQuestions(nodes);
  $('project-suggestions').innerHTML = questions.length ? '<span>From your project</span>' + questions.map((question) => `<button data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`).join('') : '<span>Add records to get questions tailored to this project.</span>';
  if ($('chat-suggestions')) $('chat-suggestions').innerHTML = questions.slice(0, 2).map((question) => `<button data-question="${escapeHtml(question)}">${escapeHtml(question)} →</button>`).join('');
  renderSources();

  const concerns = nodes.filter((node) => /blocked|at risk/i.test(node.status || ''));
  $('metric-blockers').textContent = concerns.length;
  $('signals').innerHTML = concerns.length
    ? concerns.slice(0, 4).map((node) => `<div class="attention-item"><span class="attention-badge">!</span><div><strong>${escapeHtml(node.name)}</strong><p>${escapeHtml(node.description || `Status: ${node.status}`)}</p></div></div>`).join('')
    : '<div class="empty-list">No blocked or at-risk items in the connected records.</div>';
}

function projectQuestions(nodes) {
  if (!nodes.length) return [];
  const questions = [];
  const task = nodes.find((node) => node.kind === 'Task' && /block/i.test(node.status || '')) || nodes.find((node) => node.kind === 'Task');
  const document = nodes.find((node) => node.kind === 'Document');
  const pr = nodes.find((node) => node.kind === 'PullRequest');
  if (task) questions.push(`What is the status of ${task.name.slice(0, 100)}?`);
  if (document) questions.push(`Summarize ${document.name.slice(0, 100)}`);
  if (pr) questions.push(`Explain ${pr.name.slice(0, 100)}`);
  if (questions.length < 3) questions.push('Give me an overview of this project');
  return questions.slice(0, 3);
}

function renderSources() {
  const sources = state.graph?.sources || [];
  $('source-list').innerHTML = sources.length ? sources.map((source) => `
    <div class="source-entry"><div><strong>${escapeHtml(source.name)}</strong><p>${escapeHtml(source.kind)} · ${source.record_count} records · Imported ${escapeHtml(new Date(source.synced_at).toLocaleString())}</p>
    ${(source.warnings || []).map((warning) => `<p class="source-warning">${escapeHtml(warning)}</p>`).join('')}</div>
    ${['github', 'jira'].includes(source.kind) ? `<button class="secondary-button" data-sync="${escapeHtml(source.id)}">Refresh source</button>` : '<span>File snapshot</span>'}</div>`).join('') : '<div class="empty-list">No tracked sources yet. Add a source to start importing your work.</div>';
}

function renderRecords() {
  if (!state.graph) return;
  const query = $('graph-search').value.toLowerCase();
  const nodes = state.graph.nodes.filter((node) => `${node.name} ${node.kind} ${node.description}`.toLowerCase().includes(query));
  $('graph-summary').textContent = `${state.graph.nodes.length} records · ${state.graph.edges.length} connections`;
  $('graph-list').innerHTML = nodes.length
    ? nodes.map((node) => `<button class="graph-record" data-record="${escapeHtml(node.id)}"><span class="record-icon">${escapeHtml(recordIcon[node.kind] || '◇')}</span><span><strong>${escapeHtml(node.name)}</strong><small>${escapeHtml(node.kind)}${node.status ? ` · ${escapeHtml(node.status)}` : ''}</small></span></button>`).join('')
    : '<div class="empty-list">No records match your search.</div>';
}

function showRecord(id) {
  if (!state.graph) return;
  const node = state.graph.nodes.find((item) => item.id === id);
  if (!node) return;
  document.querySelectorAll('[data-record]').forEach((element) => element.classList.toggle('selected', element.dataset.record === id));
  const links = state.graph.edges.filter((edge) => edge.source === id || edge.target === id).map((edge) => {
    const other = state.graph.nodes.find((item) => item.id === (edge.source === id ? edge.target : edge.source));
    if (!other) return '';
    const direction = edge.source === id ? '→' : '←';
    const label = edge.kind.replaceAll('_', ' ').toLowerCase();
    const uncertainty = edge.confidence === 'candidate' ? ' · possible match' : '';
    return `<div class="detail-link">${direction} ${escapeHtml(label)} <strong>${escapeHtml(other.name)}</strong>${uncertainty}</div>`;
  }).join('');
  $('graph-detail').innerHTML = `
    <span class="detail-kind">${escapeHtml(node.kind)} · ${escapeHtml(node.source)}</span>
    <h2>${escapeHtml(node.name)}</h2>
    <p>${escapeHtml(node.description || 'No description is available from the source.')}</p>
    ${node.status ? `<span class="detail-status">${escapeHtml(node.status)}</span>` : ''}
    <div class="detail-relationships"><h3>Connected to</h3>${links || '<p>No recorded connections.</p>'}</div>
    ${node.url ? `<a class="detail-source" target="_blank" rel="noopener" href="${escapeHtml(node.url)}">Open original record →</a>` : ''}`;
}

function renderHistory() {
  if (!state.graph) return;
  $('history-list').innerHTML = state.graph.investigations.length
    ? state.graph.investigations.map((item) => `<div class="history-row"><strong>${escapeHtml(item.question)}</strong><p>${escapeHtml(item.answer?.slice(0, 280) || '')}</p><small>${escapeHtml(item.created_at?.slice(0, 16).replace('T', ' ') || '')}</small></div>`).join('')
    : '<div class="empty-list">No past questions yet. Ask a question to start a project history.</div>';
  $('proposal-list').innerHTML = state.graph.proposals.length
    ? state.graph.proposals.map((item) => `<div class="history-row"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.description)}</p><small>${escapeHtml(item.status)} · ${escapeHtml(item.created_at?.slice(0, 16).replace('T', ' ') || '')}</small>${item.status === 'pending' ? `<div><button data-decision="${escapeHtml(item.id)}" data-approved="true">Approve</button><button data-decision="${escapeHtml(item.id)}" data-approved="false">Dismiss</button></div>` : ''}</div>`).join('')
    : '<div class="empty-list">No follow-up tasks have been proposed yet.</div>';
}

async function decideProposal(id, approved) {
  try {
    await api(`/api/proposals/${encodeURIComponent(id)}/decision`, { method: 'POST', body: JSON.stringify({ approved }) });
    toast(approved ? 'Follow-up approved in ProjectBrain.' : 'Follow-up dismissed.');
    await loadGraph();
  } catch (error) { toast(error.message); }
}

function appendMessage(kind, text, extra = '') {
  const log = $('chat-log');
  log.querySelector('.welcome-message')?.remove();
  const row = document.createElement('div');
  row.className = `chat-message ${kind}`;
  row.innerHTML = `<div class="bubble">${kind === 'assistant' ? '<div class="byline">PROJECTBRAIN</div>' : ''}${escapeHtml(text)}${extra}</div>`;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
  return row;
}

function renderEvidence(result) {
  $('trace-count').textContent = result.findings.length ? `${result.findings.length} findings from project records` : 'No supporting records found';
  $('trace-content').className = 'trace-list';
  const byId = Object.fromEntries(result.nodes.map((node) => [node.id, node]));
  const findings = result.findings.map((finding) => `
    <div class="trace-item"><small>${escapeHtml(finding.agent)}</small><strong>${escapeHtml(finding.title)}</strong>
    <p>${escapeHtml(finding.body)}</p><div class="trace-sources">${finding.entity_ids.map((id) => {
      const node = byId[id];
      if (!node) return '';
      return node.url ? `<a target="_blank" rel="noopener" href="${escapeHtml(node.url)}">${escapeHtml(node.name)} ↗</a>` : `<span>${escapeHtml(node.name)}</span>`;
    }).join('')}</div></div>`).join('');
  const paths = result.edges.slice(0, 12).map((edge) => {
    const first = byId[edge.source], second = byId[edge.target];
    if (!first || !second) return '';
    return `<div class="trace-path">${escapeHtml(first.name)} <b>— ${escapeHtml(edge.kind.replaceAll('_', ' ').toLowerCase())} →</b> ${escapeHtml(second.name)}${edge.confidence === 'candidate' ? ' <i>(possible match)</i>' : ''}</div>`;
  }).join('');
  $('trace-content').innerHTML = findings + (paths ? `<div class="trace-item"><small>Connections used</small>${paths}</div>` : '') || '<div class="empty-list">No evidence found in connected sources.</div>';
  if (result.coverage) $('trace-content').insertAdjacentHTML('afterbegin', `<p class="coverage-note">${escapeHtml(result.coverage)}</p>`);
}

async function askQuestion() {
  if (state.asking) return;
  if (!state.project || !state.graph?.nodes.length) return toast('Add a source with records to this project first.');
  const question = $('question-input').value.trim();
  if (!question) return;
  state.asking = true;
  const project = state.project;
  $('question-input').value = '';
  showView('assistant');
  appendMessage('user', question);
  const pending = appendMessage('assistant', 'Checking the connected project records…');
  $('ask-button').disabled = true;
  $('project-select').disabled = true;
  try {
    const result = await api('/api/investigations', { method: 'POST', body: JSON.stringify({ project_id: project, question, session_id: state.session }) });
    if (state.project !== project) { pending.remove(); return; }
    state.lastInvestigation = result.id;
    pending.remove();
    const extra = result.id ? `<div class="message-actions"><button data-followup="${escapeHtml(result.id)}">Suggest a follow-up task</button></div>` : '';
    appendMessage('assistant', result.answer, extra);
    renderEvidence(result);
    await loadGraph();
  } catch (error) {
    pending.remove();
    appendMessage('assistant', `I could not complete that question: ${error.message}`);
  } finally { state.asking = false; $('ask-button').disabled = false; $('project-select').disabled = false; }
}

async function proposeFollowup(investigationId) {
  const title = 'Review this project investigation';
  try {
    await api('/api/proposals', { method: 'POST', body: JSON.stringify({ investigation_id: investigationId, title, description: 'Review the answer and supporting project records before choosing a next step.' }) });
    toast('Follow-up task added for your review.');
    await loadGraph();
    showView('activity');
  } catch (error) { toast(error.message); }
}

async function importRepository() {
  const url = $('repo-url').value.trim();
  if (!url) return toast('Enter a GitHub repository URL.');
  setImportBusy(true, 'Reading repository pages and building connections…');
  try {
    const result = await api('/api/projects/import/github', { method: 'POST', body: JSON.stringify({ url, project_id: $('import-destination').value || null }) });
    $('source-dialog').close();
    changeProject(result.project_id);
    toast(`Added ${result.nodes} records from GitHub.`);
    await loadProjects();
  } catch (error) { $('import-feedback').textContent = error.message; }
  finally { setImportBusy(false); }
}

async function uploadDocument() {
  const file = $('document-file').files[0];
  if (!file) return toast('Choose a document first.');
  const project = $('import-destination').value;
  if (!project) return toast('Select or create a project for this file.');
  if (file.size > 5 * 1024 * 1024) return toast('Choose a file smaller than 5 MB.');
  setImportBusy(true, 'Reading your file and connecting its records…');
  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/api/projects/${encodeURIComponent(project)}/imports`, { method: 'POST', body: form });
    const result = await response.json().catch(() => ({detail: 'The server could not read this file.'}));
    if (!response.ok) throw new Error(result.detail || 'Could not add the document');
    $('source-dialog').close();
    changeProject(project);
    toast(`Imported ${result.nodes} records into the project.`);
    await loadProjects();
  } catch (error) { $('import-feedback').textContent = error.message; }
  finally { setImportBusy(false); }
}

function setImportBusy(busy, message) {
  $('source-dialog').querySelectorAll('button, input, select').forEach((element) => { element.disabled = busy; });
  if (message) $('import-feedback').textContent = message;
}

function changeProject(id) {
  if (state.project === id) return;
  state.project = id;
  state.graph = null;
  state.lastInvestigation = null;
  state.loading++;
  localStorage.setItem('projectbrain-project', id);
  $('chat-log').innerHTML = '<div class="welcome-message"><h2>Ask about this project</h2><p>Your answers will use the sources connected to this project.</p><div class="suggestions" id="chat-suggestions"></div></div>';
  $('trace-count').textContent = 'No question asked yet';
  $('trace-content').className = 'trace-empty';
  $('trace-content').textContent = 'Evidence from this project will appear here.';
  $('graph-detail').innerHTML = '<div class="detail-empty">Select a record to see its details.</div>';
  $('graph-list').innerHTML = '';
  $('project-name').textContent = 'Loading project…';
  $('project-description').textContent = '';
  $('source-list').innerHTML = '';
  $('signals').innerHTML = '';
  $('project-suggestions').innerHTML = '';
  ['metric-nodes', 'metric-investigations', 'metric-blockers'].forEach((key) => { $(key).textContent = '—'; });
  $('history-list').innerHTML = '';
  $('proposal-list').innerHTML = '';
  $('graph-search').value = '';
}

function openSources() {
  $('import-destination').value = state.project || '';
  $('import-feedback').textContent = '';
  $('source-dialog').showModal();
}

async function importJira() {
  const reference = $('jira-reference').value.trim();
  if (!reference) return toast('Enter a Jira ticket URL, ticket key, or project key.');
  setImportBusy(true, 'Reading Jira tickets and their relationships…');
  try {
    const result = await api('/api/projects/import/jira', { method: 'POST', body: JSON.stringify({ reference, project_id: $('import-destination').value || null }) });
    changeProject(result.project_id);
    $('source-dialog').close();
    await loadProjects();
    toast(`Imported ${result.nodes} Jira records.`);
  } catch (error) { $('import-feedback').textContent = error.message; }
  finally { setImportBusy(false); }
}

async function syncSource(button) {
  button.disabled = true;
  button.textContent = 'Refreshing…';
  try {
    await api('/api/sources/sync', { method: 'POST', body: JSON.stringify({ project_id: state.project, source_id: button.dataset.sync }) });
    await loadGraph();
    toast('Source refreshed. New questions will use the updated records.');
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = 'Refresh source'; }
}

document.querySelectorAll('[data-view]').forEach((element) => element.addEventListener('click', () => showView(element.dataset.view)));
document.querySelectorAll('[data-go]').forEach((element) => element.addEventListener('click', () => showView(element.dataset.go)));
document.addEventListener('click', (event) => {
  const example = event.target.closest('[data-question]');
  if (example) { $('question-input').value = example.dataset.question; askQuestion(); }
  const record = event.target.closest('[data-record]');
  if (record) showRecord(record.dataset.record);
  const decision = event.target.closest('[data-decision]');
  if (decision) decideProposal(decision.dataset.decision, decision.dataset.approved === 'true');
  const followup = event.target.closest('[data-followup]');
  if (followup) proposeFollowup(followup.dataset.followup);
  const sync = event.target.closest('[data-sync]');
  if (sync) syncSource(sync);
  const tab = event.target.closest('[data-source-tab]');
  if (tab) {
    document.querySelectorAll('[data-source-tab]').forEach((element) => element.classList.toggle('active', element === tab));
    document.querySelectorAll('[data-source-pane]').forEach((element) => { element.hidden = element.dataset.sourcePane !== tab.dataset.sourceTab; });
  }
});
$('quick-ask-form').addEventListener('submit', (event) => {
  event.preventDefault();
  $('question-input').value = $('quick-question').value;
  $('quick-question').value = '';
  askQuestion();
});
$('ask-form').addEventListener('submit', (event) => { event.preventDefault(); askQuestion(); });
$('question-input').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); askQuestion(); }
});
$('graph-search').addEventListener('input', renderRecords);
$('project-select').addEventListener('change', (event) => { changeProject(event.target.value); loadGraph(); });
$('refresh').addEventListener('click', loadProjects);
$('add-source').addEventListener('click', openSources);
$('top-add-source').addEventListener('click', openSources);
$('empty-add-source').addEventListener('click', openSources);
$('import-repo').addEventListener('click', importRepository);
$('import-jira').addEventListener('click', importJira);
$('upload-document').addEventListener('click', uploadDocument);
$('create-project').addEventListener('click', async () => {
  const name = $('new-project-name').value.trim();
  if (name.length < 2) return toast('Give the project a name with at least two characters.');
  setImportBusy(true, 'Creating project…');
  try {
    const result = await api('/api/projects', { method: 'POST', body: JSON.stringify({ name }) });
    changeProject(result.project_id);
    await loadProjects();
    $('import-destination').value = state.project;
    $('import-feedback').textContent = 'Project created. Now choose a source to add.';
  } catch (error) { $('import-feedback').textContent = error.message; }
  finally { setImportBusy(false); }
});
$('load-demo').addEventListener('click', async () => {
  $('load-demo').disabled = true;
  try { const result = await api('/api/demo/seed', { method: 'POST' }); changeProject(result.project_id); await loadProjects(); }
  catch (error) { toast(error.message); }
  finally { $('load-demo').disabled = false; }
});
api('/api/connectors').then((config) => {
  $('jira-config-status').textContent = config.jira_configured ? 'Jira Cloud is connected. Import a ticket or all visible tickets from a project.' : 'Jira Cloud needs server credentials. Expand the setup instructions below.';
  $('github-config-status').textContent = config.github_authenticated ? 'Server token configured. Repositories are limited to its permissions.' : 'Public repositories work now. Private repositories require a server GITHUB_TOKEN.';
  $('answer-mode').textContent = config.answer_mode === 'model' ? 'AI answers with source evidence' : 'Evidence mode · source excerpts and connections';
}).catch(() => {});
$('topbar-date').textContent = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' }).format(new Date());
loadProjects();
