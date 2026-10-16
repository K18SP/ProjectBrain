const state = {
  project: 'atlas',
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
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
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

    let projects = await api('/api/projects');
    if (!projects.length) {
      await api('/api/demo/seed', { method: 'POST' });
      projects = await api('/api/projects');
    }

    const selector = $('project-select');
    selector.innerHTML = projects.map((project) => `<option value="${escapeHtml(project.id)}">${escapeHtml(project.name)}</option>`).join('');
    if (!projects.some((project) => project.id === state.project)) state.project = projects[0].id;
    selector.value = state.project;
    await loadGraph();
  } catch (error) {
    setConnectionStatus(false);
    toast(error.message);
  }
}

async function loadGraph() {
  try {
    state.graph = await api(`/api/projects/${encodeURIComponent(state.project)}/graph`);
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

  const concerns = nodes.filter((node) => /blocked|at risk/i.test(node.status || ''));
  $('metric-blockers').textContent = concerns.length;
  $('signals').innerHTML = concerns.length
    ? concerns.slice(0, 4).map((node) => `<div class="attention-item"><span class="attention-badge">!</span><div><strong>${escapeHtml(node.name)}</strong><p>${escapeHtml(node.description || `Status: ${node.status}`)}</p></div></div>`).join('')
    : '<div class="empty-list">No blocked or at-risk items in the connected records.</div>';
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
}

async function askQuestion() {
  const question = $('question-input').value.trim();
  if (!question) return;
  $('question-input').value = '';
  showView('assistant');
  appendMessage('user', question);
  const pending = appendMessage('assistant', 'Checking the connected project records…');
  $('ask-button').disabled = true;
  try {
    const result = await api('/api/investigations', { method: 'POST', body: JSON.stringify({ project_id: state.project, question, session_id: state.session }) });
    state.lastInvestigation = result.id;
    pending.remove();
    const extra = result.id ? `<div class="message-actions"><button data-followup="${escapeHtml(result.id)}">Suggest a follow-up task</button></div>` : '';
    appendMessage('assistant', result.answer, extra);
    renderEvidence(result);
    await loadGraph();
  } catch (error) {
    pending.remove();
    appendMessage('assistant', `I could not complete that question: ${error.message}`);
  } finally { $('ask-button').disabled = false; }
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
  if (!url) return toast('Enter a public GitHub repository URL.');
  $('import-repo').disabled = true;
  try {
    const result = await api('/api/projects/import/github', { method: 'POST', body: JSON.stringify({ url }) });
    $('source-dialog').close();
    state.project = result.project_id;
    toast(`Added ${result.nodes} records from GitHub.`);
    await loadProjects();
  } catch (error) { toast(error.message); }
  finally { $('import-repo').disabled = false; }
}

async function uploadDocument() {
  const file = $('document-file').files[0];
  if (!file) return toast('Choose a document first.');
  $('upload-document').disabled = true;
  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/api/projects/${encodeURIComponent(state.project)}/documents`, { method: 'POST', body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not add the document');
    $('source-dialog').close();
    toast(`Added ${result.nodes} document records to the project.`);
    await loadGraph();
  } catch (error) { toast(error.message); }
  finally { $('upload-document').disabled = false; }
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
$('project-select').addEventListener('change', (event) => { state.project = event.target.value; loadGraph(); });
$('refresh').addEventListener('click', loadProjects);
$('add-source').addEventListener('click', () => $('source-dialog').showModal());
$('top-add-source').addEventListener('click', () => $('source-dialog').showModal());
$('import-repo').addEventListener('click', importRepository);
$('upload-document').addEventListener('click', uploadDocument);
$('topbar-date').textContent = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' }).format(new Date());
loadProjects();
