import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Page, MenuItem

# HTML content for the projects page with popup modal forms and actions
projects_html = """
<div class="projects-wrapper">
  <div class="header-actions">
    <h2>Ongoing Projects Logs</h2>
    <div style="display: flex; gap: 1rem; align-items: center;">
      <div class="view-toggles">
        <button id="view-grouped-btn" class="view-toggle-btn active" onclick="setViewMode('grouped')">Grouped</button>
        <button id="view-flat-btn" class="view-toggle-btn" onclick="setViewMode('flat')">Flat List</button>
      </div>
      <button class="add-project-btn" onclick="openAddModal()">＋ Add New Project</button>
    </div>
  </div>
  
  <div id="projects-container">
    <div class="loading">Loading projects list...</div>
  </div>
</div>

<!-- Add/Edit Modal -->
<div id="project-modal" class="modal-overlay" onclick="if(event.target===this) closeFormModal()">
  <div class="modal-box">
    <div class="modal-header">
      <h3 class="modal-title" id="modal-title">Add New Project</h3>
      <button class="close-btn" onclick="closeFormModal()">&times;</button>
    </div>
    <form id="project-form" onsubmit="handleFormSubmit(event)">
      <div class="form-row">
        <label for="proj-title">Project Title</label>
        <input type="text" id="proj-title" class="form-input" required autocomplete="off">
      </div>
      <div class="form-row">
        <label for="proj-category">Category</label>
        <input type="text" id="proj-category" list="category-suggestions" class="form-input" required autocomplete="off">
        <datalist id="category-suggestions"></datalist>
      </div>
      <div class="form-row">
        <label for="proj-parent">Parent Project</label>
        <select id="proj-parent" class="form-select">
          <option value="">-- None (Root Project) --</option>
        </select>
      </div>
      <div class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div>
          <label for="proj-status">Status</label>
          <select id="proj-status" class="form-select" required>
            <option value="idea">Idea</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="paused">Paused</option>
          </select>
        </div>
        <div>
          <label for="proj-rank">Rank</label>
          <input type="number" id="proj-rank" class="form-input" min="0" value="9000" required autocomplete="off">
        </div>
      </div>
      <div class="form-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
        <div>
          <label for="proj-start-date">Start Date</label>
          <input type="date" id="proj-start-date" class="form-input">
        </div>
        <div>
          <label for="proj-end-date">End Date</label>
          <input type="date" id="proj-end-date" class="form-input">
        </div>
      </div>
      <div class="form-row">
        <label for="proj-desc">Description</label>
        <textarea id="proj-desc" class="form-textarea" placeholder="Project details..."></textarea>
      </div>
      <div class="form-actions">
        <button type="button" class="editorial-btn" style="background-color: var(--accent-light); color: var(--text-color); margin-top: 0;" onclick="closeFormModal()">Cancel</button>
        <button type="submit" id="save-project-btn" class="editorial-btn" style="margin-top: 0;">Save Project</button>
      </div>
    </form>
  </div>
</div>

<!-- Delete Confirmation Modal -->
<div id="delete-modal" class="modal-overlay" onclick="if(event.target===this) closeDeleteModal()">
  <div class="modal-box" style="max-width: 400px; text-align: center;">
    <div class="modal-header" style="justify-content: center; border-bottom: none; margin-bottom: 0.5rem;">
      <h3 class="modal-title">Confirm Delete</h3>
    </div>
    <p style="font-size: 0.95rem; margin-bottom: 1.5rem; color: var(--text-muted);">
      Are you sure you want to delete <strong id="delete-project-title">this project</strong>? This action cannot be undone.
    </p>
    <div style="display: flex; justify-content: center; gap: 1rem;">
      <button class="editorial-btn" style="background-color: var(--accent-light); color: var(--text-color); margin-top: 0;" onclick="closeDeleteModal()">Cancel</button>
      <button id="delete-confirm-btn" class="editorial-btn" style="background-color: #dc2626; color: #ffffff; margin-top: 0;" onclick="confirmDelete()">Delete</button>
    </div>
  </div>
</div>

<style>
  .projects-wrapper {
    font-family: var(--font-sans);
    color: var(--text-color);
    position: relative;
    min-height: 100%;
  }
  .header-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }
  .add-project-btn {
    padding: 0.6rem 1.2rem;
    background-color: var(--accent-color);
    color: #ffffff;
    border: none;
    border-radius: 4px;
    font-family: var(--font-sans);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }
  .add-project-btn:hover {
    background-color: #8c6446;
  }
  .view-toggles {
    display: flex;
    border: 1px solid var(--accent-color);
    border-radius: 4px;
    overflow: hidden;
    background-color: #ffffff;
  }
  .view-toggle-btn {
    padding: 0.4rem 0.8rem;
    background-color: transparent;
    color: var(--accent-color);
    border: none;
    font-family: var(--font-sans);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .view-toggle-btn.active {
    background-color: var(--accent-color);
    color: #ffffff;
  }
  .view-toggle-btn:hover:not(.active) {
    background-color: var(--accent-light);
  }
  .show-all-btn {
    padding: 0.6rem 1.2rem;
    background-color: transparent;
    color: var(--accent-color);
    border: 1px solid var(--accent-color);
    border-radius: 4px;
    font-family: var(--font-sans);
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .show-all-btn:hover {
    background-color: var(--accent-light);
  }
  .show-all-btn.active {
    background-color: var(--accent-color);
    color: #ffffff;
  }
  .category-section {
    margin-bottom: 2.5rem;
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
  }
  .category-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1.2rem;
    padding-bottom: 0.5rem;
  }
  .category-title {
    font-family: var(--font-serif);
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--accent-color);
    margin: 0;
  }
  .project-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    text-align: left;
  }
  .project-table th {
    border-bottom: 2px solid var(--text-color);
    padding: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    position: relative;
    transition: background-color 0.2s ease;
  }
  .project-table th:hover {
    background-color: var(--accent-light);
  }
  .project-table th::after {
    content: ' ↕';
    font-size: 0.75rem;
    color: var(--text-muted);
    opacity: 0.4;
    margin-left: 0.3rem;
  }
  .project-table th.sort-asc::after {
    content: ' ▲';
    opacity: 1;
    color: var(--accent-color);
  }
  .project-table th.sort-desc::after {
    content: ' ▼';
    opacity: 1;
    color: var(--accent-color);
  }
  .project-table td {
    border-bottom: 1px solid var(--border-color);
    padding: 0.8rem;
    vertical-align: top;
    line-height: 1.5;
  }
  .project-table tr:hover {
    background-color: var(--accent-light);
  }
  .status-badge {
    display: inline-block;
    padding: 0.2rem 0.5rem;
    border-radius: 3px;
    font-weight: 500;
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
  }
  .status-idea {
    background-color: #f1f1ee;
    color: var(--text-muted);
    border: 1px solid var(--border-dark);
  }
  .status-in_progress {
    background-color: var(--accent-light);
    color: var(--accent-color);
    border: 1px solid var(--border-color);
  }
  .status-completed {
    background-color: #d1fae5;
    color: #065f46;
    border: 1px solid #a7f3d0;
  }
  .status-paused {
    background-color: #fee2e2;
    color: #dc2626;
    border: 1px solid #fecaca;
  }
  .loading {
    padding: 2rem;
    text-align: center;
    color: var(--text-muted);
    font-style: italic;
  }
  .error-message {
    color: #dc2626;
    padding: 1rem;
    background-color: #fee2e2;
    border: 1px solid #fecaca;
    border-radius: 4px;
    margin-top: 1rem;
  }
  .project-desc {
    color: var(--text-muted);
    max-width: 350px;
  }

  /* Modals */
  .modal-overlay {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(43, 43, 42, 0.4);
    display: none;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    backdrop-filter: blur(2px);
  }
  .modal-box {
    background-color: var(--bg-color);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    width: 90%;
    max-width: 500px;
    padding: 2rem;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
    position: relative;
    animation: slideUp 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
  }
  @keyframes slideUp {
    from { transform: translateY(15px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 0.5rem;
  }
  .modal-title {
    font-family: var(--font-serif);
    font-size: 1.25rem;
    font-weight: 500;
    color: var(--text-color);
  }
  .close-btn {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: var(--text-muted);
    line-height: 1;
  }
  .close-btn:hover {
    color: var(--text-color);
  }
  .form-row {
    margin-bottom: 1.2rem;
  }
  .form-row label {
    display: block;
    font-family: var(--font-sans);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.4rem;
    color: var(--text-color);
  }
  .form-input, .form-select, .form-textarea {
    width: 100%;
    padding: 0.6rem 0.8rem;
    border: 1px solid var(--border-dark);
    border-radius: 4px;
    background-color: #ffffff;
    font-family: var(--font-sans);
    font-size: 0.85rem;
    outline: none;
    transition: border-color 0.2s;
  }
  .form-input:focus, .form-select:focus, .form-textarea:focus {
    border-color: var(--accent-color);
  }
  .form-textarea {
    resize: vertical;
    min-height: 80px;
    font-family: var(--font-sans);
  }
  .form-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
    margin-top: 1.5rem;
  }

  /* Actions buttons on rows */
  .action-btn {
    padding: 0.25rem 0.5rem;
    font-size: 0.7rem;
    border: 1px solid var(--border-color);
    border-radius: 3px;
    background-color: #ffffff;
    cursor: pointer;
    transition: all 0.2s ease;
    font-family: var(--font-sans);
    text-transform: uppercase;
    font-weight: 600;
    margin-left: 0.3rem;
  }
  .action-btn-edit {
    color: var(--accent-color);
    border-color: var(--accent-color);
  }
  .action-btn-edit:hover {
    background-color: var(--accent-light);
  }
  .action-btn-delete {
    color: #dc2626;
    border-color: #fca5a5;
  }
  .action-btn-delete:hover {
    background-color: #fee2e2;
  }
  
  /* Subproject custom styling */
  .subproject-row {
    background-color: var(--accent-light) !important;
  }
  .subproject-indent {
    padding-left: 2rem !important;
    position: relative;
    display: inline-block;
  }
  .subproject-indent::before {
    content: "└─ ";
    color: var(--accent-color);
    font-weight: bold;
    margin-right: 0.5rem;
  }
  .toggle-btn {
    background: none;
    border: none;
    color: var(--accent-color);
    cursor: pointer;
    font-size: 0.75rem;
    padding: 0 0.3rem 0 0;
    vertical-align: middle;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    height: 1.1rem;
    transition: transform 0.2s ease;
  }
  .toggle-btn:hover {
    color: var(--text-color);
  }
</style>

<script>
  let activeProjectId = null;
  let allCategories = [];
  let parentListenersAttached = false;
  let expandedProjects = {}; // Tracks expanded parent project IDs
  let currentSort = { colIndex: 0, isAsc: true }; // Sort by rank (colIndex 0) ascending by default

  function toggleProject(projectId) {
    expandedProjects[projectId] = !expandedProjects[projectId];
    renderProjects();
  }

  function getComparator(colIndex, isAsc, isFlat = false) {
    return (a, b) => {
      let valA = '';
      let valB = '';
      
      if (isFlat) {
        if (colIndex === 0) { // Rank
          valA = a.rank !== undefined && a.rank !== null ? a.rank : 9000;
          valB = b.rank !== undefined && b.rank !== null ? b.rank : 9000;
          return isAsc ? valA - valB : valB - valA;
        } else if (colIndex === 1) { // Title
          valA = a.title || '';
          valB = b.title || '';
        } else if (colIndex === 2) { // Category
          valA = a.category || '';
          valB = b.category || '';
        } else if (colIndex === 3) { // Status
          valA = a.status || '';
          valB = b.status || '';
        } else if (colIndex === 4) { // Start Date
          valA = a.start_date ? new Date(a.start_date) : new Date(0);
          valB = b.start_date ? new Date(b.start_date) : new Date(0);
          return isAsc ? valA - valB : valB - valA;
        } else if (colIndex === 5) { // End Date
          valA = a.end_date ? new Date(a.end_date) : new Date(0);
          valB = b.end_date ? new Date(b.end_date) : new Date(0);
          return isAsc ? valA - valB : valB - valA;
        }
      } else {
        if (colIndex === 0) { // Rank
          valA = a.rank !== undefined && a.rank !== null ? a.rank : 9000;
          valB = b.rank !== undefined && b.rank !== null ? b.rank : 9000;
          return isAsc ? valA - valB : valB - valA;
        } else if (colIndex === 1) { // Title
          valA = a.title || '';
          valB = b.title || '';
        } else if (colIndex === 2) { // Status
          valA = a.status || '';
          valB = b.status || '';
        } else if (colIndex === 3) { // Start Date
          valA = a.start_date ? new Date(a.start_date) : new Date(0);
          valB = b.start_date ? new Date(b.start_date) : new Date(0);
          return isAsc ? valA - valB : valB - valA;
        } else if (colIndex === 4) { // End Date
          valA = a.end_date ? new Date(a.end_date) : new Date(0);
          valB = b.end_date ? new Date(b.end_date) : new Date(0);
          return isAsc ? valA - valB : valB - valA;
        }
      }
      
      return isAsc
        ? String(valA).localeCompare(String(valB), undefined, { numeric: true, sensitivity: 'base' })
        : String(valB).localeCompare(String(valA), undefined, { numeric: true, sensitivity: 'base' });
    };
  }

  function populateParentSuggestions(currentProjectId = null) {
    const parentSelect = document.getElementById('proj-parent');
    if (!parentSelect) return;
    
    parentSelect.innerHTML = '<option value="">-- None (Root Project) --</option>';
    
    const sortedForParent = [...cachedProjects].sort((a, b) => {
      const catA = a.category || '';
      const catB = b.category || '';
      if (catA !== catB) return catA.localeCompare(catB);
      return (a.title || '').localeCompare(b.title || '');
    });

    let currentOptgroup = null;
    
    sortedForParent.forEach(p => {
      if (currentProjectId && p.id === currentProjectId) return;
      if (p.parent) return; // Only allow root projects as parents

      const cat = p.category || 'General';
      if (!currentOptgroup || currentOptgroup.label !== cat) {
        currentOptgroup = document.createElement('optgroup');
        currentOptgroup.label = cat;
        parentSelect.appendChild(currentOptgroup);
      }
      
      const option = document.createElement('option');
      option.value = p.id;
      option.textContent = p.title;
      currentOptgroup.appendChild(option);
    });
  }

  function resizeIframe() {
    if (window.parent && window.parent !== window) {
      try {
        const iframes = window.parent.document.querySelectorAll('iframe');
        for (const iframe of iframes) {
          if (iframe.contentWindow === window) {
            iframe.style.height = document.documentElement.scrollHeight + 60 + 'px';
            break;
          }
        }
      } catch (e) {
        console.error("Failed to resize parent iframe:", e);
      }
    }
  }

  function positionModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal || modal.style.display !== 'flex') return;
    
    const modalBox = modal.querySelector('.modal-box');
    if (!modalBox) return;

    if (window.parent && window.parent !== window) {
      try {
        const iframes = window.parent.document.querySelectorAll('iframe');
        let myIframe = null;
        for (const iframe of iframes) {
          if (iframe.contentWindow === window) {
            myIframe = iframe;
            break;
          }
        }
        if (myIframe) {
          const rect = myIframe.getBoundingClientRect();
          const parentHeight = window.parent.innerHeight;
          let centerY = -rect.top + (parentHeight / 2);
          
          const modalHeight = modalBox.offsetHeight || 380;
          const pageHeight = document.documentElement.scrollHeight;
          const halfModal = modalHeight / 2;
          
          if (pageHeight > modalHeight) {
            if (centerY - halfModal < 10) {
              centerY = halfModal + 10;
            } else if (centerY + halfModal > pageHeight - 10) {
              centerY = pageHeight - halfModal - 10;
            }
          } else {
            centerY = pageHeight / 2;
          }

          modalBox.style.position = 'absolute';
          modalBox.style.top = centerY + 'px';
          modalBox.style.left = '50%';
          modalBox.style.transform = 'translate(-50%, -50%)';
          modalBox.style.margin = '0';
        }
      } catch (e) {
        console.error("Failed to position modal:", e);
      }
    }
  }

  function handleParentScrollOrResize() {
    positionModal('project-modal');
    positionModal('delete-modal');
  }

  function attachParentListeners() {
    if (window.parent && window.parent !== window && !parentListenersAttached) {
      try {
        window.parent.addEventListener('scroll', handleParentScrollOrResize);
        window.parent.addEventListener('resize', handleParentScrollOrResize);
        parentListenersAttached = true;
      } catch (e) {
        console.error("Failed to attach parent listeners:", e);
      }
    }
  }

  function removeParentListeners() {
    if (window.parent && window.parent !== window && parentListenersAttached) {
      try {
        window.parent.removeEventListener('scroll', handleParentScrollOrResize);
        window.parent.removeEventListener('resize', handleParentScrollOrResize);
        parentListenersAttached = false;
      } catch (e) {
        console.error("Failed to remove parent listeners:", e);
      }
    }
  }

  function openAddModal() {
    activeProjectId = null;
    document.getElementById('modal-title').textContent = 'Add New Project';
    document.getElementById('project-form').reset();
    document.getElementById('proj-status').value = 'idea'; // Default to idea
    document.getElementById('proj-rank').value = 9000;
    populateCategorySuggestions();
    populateParentSuggestions(null);
    document.getElementById('proj-parent').value = '';
    
    const modal = document.getElementById('project-modal');
    modal.style.display = 'flex';
    resizeIframe();
    attachParentListeners();
    positionModal('project-modal');
    requestAnimationFrame(() => positionModal('project-modal'));
  }

  function openEditModal(projectJsonStr) {
    const p = JSON.parse(decodeURIComponent(projectJsonStr));
    activeProjectId = p.id;
    document.getElementById('modal-title').textContent = 'Edit Project';
    
    document.getElementById('proj-title').value = p.title || '';
    document.getElementById('proj-category').value = p.category || '';
    document.getElementById('proj-status').value = p.status || 'idea';
    document.getElementById('proj-rank').value = p.rank !== undefined && p.rank !== null ? p.rank : 9000;
    document.getElementById('proj-start-date').value = p.start_date || '';
    document.getElementById('proj-end-date').value = p.end_date || '';
    document.getElementById('proj-desc').value = p.description || '';
    
    populateCategorySuggestions();
    populateParentSuggestions(p.id);
    document.getElementById('proj-parent').value = p.parent || '';
    
    const modal = document.getElementById('project-modal');
    modal.style.display = 'flex';
    resizeIframe();
    attachParentListeners();
    positionModal('project-modal');
    requestAnimationFrame(() => positionModal('project-modal'));
  }

  function closeFormModal() {
    document.getElementById('project-modal').style.display = 'none';
    if (document.getElementById('delete-modal').style.display !== 'flex') {
      removeParentListeners();
    }
    resizeIframe();
  }

  function openDeleteModal(projectId, projectTitle) {
    activeProjectId = projectId;
    document.getElementById('delete-project-title').textContent = projectTitle;
    
    const modal = document.getElementById('delete-modal');
    modal.style.display = 'flex';
    resizeIframe();
    attachParentListeners();
    positionModal('delete-modal');
    requestAnimationFrame(() => positionModal('delete-modal'));
  }

  function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    if (document.getElementById('project-modal').style.display !== 'flex') {
      removeParentListeners();
    }
    resizeIframe();
  }

  function populateCategorySuggestions() {
    const datalist = document.getElementById('category-suggestions');
    datalist.innerHTML = '';
    allCategories.forEach(cat => {
      const option = document.createElement('option');
      option.value = cat;
      datalist.appendChild(option);
    });
  }

  async function getCsrfToken() {
    try {
      const response = await fetch('/api/auth/csrf/');
      if (response.ok) {
        const data = await response.json();
        return data.csrfToken;
      }
    } catch (e) {
      console.error("Failed to fetch CSRF token:", e);
    }
    return null;
  }

  let cachedProjects = [];
  let showAllCategories = {};
  let showAllFlat = false;
  let viewMode = 'grouped';

  async function loadProjects() {
    const container = document.getElementById('projects-container');
    const token = localStorage.getItem('authToken');
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = 'Token ' + token;
    }

    try {
      const response = await fetch('/api/projects/', { headers });
      if (response.status === 401 || response.status === 403) {
        container.innerHTML = '<div class="error-message">🔒 Authentication required. Please sign in to view ongoing projects.</div>';
        resizeIframe();
        return;
      }
      if (!response.ok) {
        throw new Error('Failed to fetch projects data');
      }
      const data = await response.json();
      cachedProjects = data;
      renderProjects();
    } catch (err) {
      console.error(err);
      container.innerHTML = '<div class="error-message">Failed to load projects: ' + err.message + '</div>';
      resizeIframe();
    }
  }

  function toggleCategoryShowAll(cat) {
    showAllCategories[cat] = !showAllCategories[cat];
    renderProjects();
  }

  function setViewMode(mode) {
    viewMode = mode;
    document.getElementById('view-grouped-btn').classList.toggle('active', mode === 'grouped');
    document.getElementById('view-flat-btn').classList.toggle('active', mode === 'flat');
    renderProjects();
  }

  function renderProjects(projects) {
    if (projects) cachedProjects = projects;
    const container = document.getElementById('projects-container');
    
    if (!cachedProjects || cachedProjects.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); font-style: italic; padding: 2rem 0; text-align: center;">No projects recorded.</p>';
      resizeIframe();
      return;
    }

    container.innerHTML = '';

    if (viewMode === 'flat') {
      cachedProjects.sort(getComparator(currentSort.colIndex, currentSort.isAsc, true));
      renderFlatView(container);
    } else {
      renderGroupedView(container);
    }

    // Resize after DOM rendering is complete
    setTimeout(resizeIframe, 100);
  }

  function renderFlatView(container) {
    const isShowAll = !!showAllFlat;
    const displayList = isShowAll 
      ? cachedProjects 
      : cachedProjects.filter(p => p.status !== 'completed');

    const section = document.createElement('div');
    section.className = 'category-section';

    const catHeader = document.createElement('div');
    catHeader.className = 'category-header';

    const title = document.createElement('h3');
    title.className = 'category-title';
    title.textContent = 'All Projects';
    catHeader.appendChild(title);

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'show-all-btn' + (isShowAll ? ' active' : '');
    toggleBtn.style.padding = '0.4rem 0.8rem';
    toggleBtn.style.fontSize = '0.75rem';
    toggleBtn.textContent = isShowAll ? 'Hide Completed' : 'Show All';
    toggleBtn.onclick = () => {
      showAllFlat = !showAllFlat;
      renderProjects();
    };
    catHeader.appendChild(toggleBtn);

    section.appendChild(catHeader);

    const table = document.createElement('table');
    table.className = 'project-table';
    
    const thClass = (idx) => {
      if (currentSort.colIndex === idx) {
        return currentSort.isAsc ? 'class="sort-asc"' : 'class="sort-desc"';
      }
      return '';
    };

    const thead = document.createElement('thead');
    thead.innerHTML = `
      <tr>
        <th style="width: 8%;" ${thClass(0)} onclick="sortTable(this, 0)">Rank</th>
        <th style="width: 18%;" ${thClass(1)} onclick="sortTable(this, 1)">Title</th>
        <th style="width: 15%;" ${thClass(2)} onclick="sortTable(this, 2)">Category</th>
        <th style="width: 10%;" ${thClass(3)} onclick="sortTable(this, 3)">Status</th>
        <th style="width: 12%;" ${thClass(4)} onclick="sortTable(this, 4)">Start Date</th>
        <th style="width: 12%;" ${thClass(5)} onclick="sortTable(this, 5)">End Date</th>
        <th style="width: 15%;">Description</th>
        <th style="width: 10%; text-align: right;">Actions</th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    
    if (displayList.length === 0) {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td colspan="8" style="text-align: center; color: var(--text-muted); font-style: italic; padding: 1.5rem 0;">
          No active projects. Click "Show All" to view completed projects.
        </td>
      `;
      tbody.appendChild(row);
    } else {
      displayList.forEach(p => {
        const row = document.createElement('tr');
        if (p.parent) {
          row.className = 'subproject-row';
        }
        
        let descContent = p.description || '';
        if (p.render_as_html) {
          // Keep it as raw HTML
        } else {
          descContent = escapeHTML(descContent);
        }

        const projectJsonStr = encodeURIComponent(JSON.stringify(p));
        
        let titleCellContent = '';
        const parentProj = p.parent ? cachedProjects.find(x => x.id === p.parent) : null;
        if (parentProj) {
          titleCellContent = `
            <span class="subproject-indent">${escapeHTML(p.title)}</span>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 0.15rem; padding-left: 2rem;">
              ↳ Subproject of: <strong>${escapeHTML(parentProj.title)}</strong>
            </div>
          `;
        } else {
          titleCellContent = `<strong>${escapeHTML(p.title)}</strong>`;
        }

        row.innerHTML = `
          <td style="font-weight: 600; color: var(--accent-color);">${p.rank !== undefined && p.rank !== null ? p.rank : 9000}</td>
          <td ${p.parent ? 'style="padding-left: 0;"' : ''}>${titleCellContent}</td>
          <td style="color: var(--text-muted); font-style: italic;">${escapeHTML(p.category || 'General')}</td>
          <td><span class="status-badge status-${p.status}">${formatStatus(p.status)}</span></td>
          <td>${p.start_date || '-'}</td>
          <td>${p.end_date || '-'}</td>
          <td class="project-desc">${descContent}</td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="action-btn action-btn-edit" onclick="openEditModal('${projectJsonStr}')">Edit</button>
            <button class="action-btn action-btn-delete" onclick="openDeleteModal(${p.id}, '${escapeHTML(p.title).replace(/'/g, "\\'")}')">Delete</button>
          </td>
        `;
        tbody.appendChild(row);
      });
    }
    
    table.appendChild(tbody);
    section.appendChild(table);
    container.appendChild(section);
  }

  function renderGroupedView(container) {
    const categories = {};
    const categorySet = new Set();
    
    cachedProjects.forEach(p => {
      if (p.category) categorySet.add(p.category);
    });

    cachedProjects.forEach(p => {
      const cat = p.category || 'General';
      categorySet.add(cat);
      if (!categories[cat]) categories[cat] = [];
      categories[cat].push(p);
    });
    allCategories = Array.from(categorySet).sort();

    Object.keys(categories).forEach(cat => {
      const list = categories[cat] || [];
      if (list.length === 0) return;

      const rootProjects = list.filter(p => !p.parent || !list.some(parent => parent.id == p.parent));
      
      const subProjectsMap = {};
      list.forEach(p => {
        if (p.parent) {
          if (!subProjectsMap[p.parent]) subProjectsMap[p.parent] = [];
          subProjectsMap[p.parent].push(p);
        }
      });

      rootProjects.sort(getComparator(currentSort.colIndex, currentSort.isAsc, false));

      const isShowAll = !!showAllCategories[cat];
      const displayRootList = isShowAll 
        ? rootProjects 
        : rootProjects.filter(p => p.status !== 'completed');

      const getDisplaySubprojects = (parentId) => {
        const subs = subProjectsMap[parentId] || [];
        const sortedSubs = [...subs].sort((a, b) => {
          const rankA = a.rank !== undefined && a.rank !== null ? a.rank : 9000;
          const rankB = b.rank !== undefined && b.rank !== null ? b.rank : 9000;
          if (rankA !== rankB) return rankA - rankB;
          return (a.title || '').localeCompare(b.title || '');
        });
        return isShowAll ? sortedSubs : sortedSubs.filter(p => p.status !== 'completed');
      };

      const section = document.createElement('div');
      section.className = 'category-section';

      const catHeader = document.createElement('div');
      catHeader.className = 'category-header';

      const title = document.createElement('h3');
      title.className = 'category-title';
      title.textContent = cat;
      catHeader.appendChild(title);

      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'show-all-btn' + (isShowAll ? ' active' : '');
      toggleBtn.style.padding = '0.4rem 0.8rem';
      toggleBtn.style.fontSize = '0.75rem';
      toggleBtn.textContent = isShowAll ? 'Hide Completed' : 'Show All';
      toggleBtn.onclick = () => toggleCategoryShowAll(cat);
      catHeader.appendChild(toggleBtn);

      section.appendChild(catHeader);

      const table = document.createElement('table');
      table.className = 'project-table';
      
      const thClass = (idx) => {
        if (currentSort.colIndex === idx) {
          return currentSort.isAsc ? 'class="sort-asc"' : 'class="sort-desc"';
        }
        return '';
      };

      const thead = document.createElement('thead');
      thead.innerHTML = `
        <tr>
          <th style="width: 8%;" ${thClass(0)} onclick="sortTable(this, 0)">Rank</th>
          <th style="width: 20%;" ${thClass(1)} onclick="sortTable(this, 1)">Title</th>
          <th style="width: 12%;" ${thClass(2)} onclick="sortTable(this, 2)">Status</th>
          <th style="width: 12%;" ${thClass(3)} onclick="sortTable(this, 3)">Start Date</th>
          <th style="width: 12%;" ${thClass(4)} onclick="sortTable(this, 4)">End Date</th>
          <th style="width: 21%;">Description</th>
          <th style="width: 15%; text-align: right;">Actions</th>
        </tr>
      `;
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      
      const renderRow = (p, isSubproject = false) => {
        const row = document.createElement('tr');
        if (isSubproject) {
          row.className = 'subproject-row';
        }
        
        let descContent = p.description || '';
        if (p.render_as_html) {
          // Keep it as raw HTML
        } else {
          descContent = escapeHTML(descContent);
        }

        const projectJsonStr = encodeURIComponent(JSON.stringify(p));
        
        let titleCellContent = '';
        if (isSubproject) {
          titleCellContent = `<span class="subproject-indent">${escapeHTML(p.title)}</span>`;
        } else {
          const displaySubs = getDisplaySubprojects(p.id);
          const hasSubs = displaySubs.length > 0;
          const isExpanded = !!expandedProjects[p.id];
          
          if (hasSubs) {
            titleCellContent = `
              <button class="toggle-btn" onclick="toggleProject(${p.id}); event.stopPropagation();">
                ${isExpanded ? '▼' : '▶'}
              </button>
              <strong>${escapeHTML(p.title)}</strong>
              <span class="badge badge-active" style="margin-left: 0.5rem; font-size: 0.65rem; padding: 0.1rem 0.3rem; text-transform: uppercase;">
                ${displaySubs.length} subproject${displaySubs.length > 1 ? 's' : ''}
              </span>
            `;
          } else {
            titleCellContent = escapeHTML(p.title);
          }
        }

        row.innerHTML = `
          <td style="font-weight: 600; color: var(--accent-color);">${p.rank !== undefined && p.rank !== null ? p.rank : 9000}</td>
          <td ${isSubproject ? 'style="padding-left: 0;"' : ''}>${titleCellContent}</td>
          <td><span class="status-badge status-${p.status}">${formatStatus(p.status)}</span></td>
          <td>${p.start_date || '-'}</td>
          <td>${p.end_date || '-'}</td>
          <td class="project-desc">${descContent}</td>
          <td style="text-align: right; white-space: nowrap;">
            <button class="action-btn action-btn-edit" onclick="openEditModal('${projectJsonStr}')">Edit</button>
            <button class="action-btn action-btn-delete" onclick="openDeleteModal(${p.id}, '${escapeHTML(p.title).replace(/'/g, "\\'")}')">Delete</button>
          </td>
        `;
        return row;
      };

      if (displayRootList.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td colspan="7" style="text-align: center; color: var(--text-muted); font-style: italic; padding: 1.5rem 0;">
            No active projects. Click "Show All" to view completed projects.
          </td>
        `;
        tbody.appendChild(row);
      } else {
        displayRootList.forEach(p => {
          tbody.appendChild(renderRow(p, false));
          
          const displaySubs = getDisplaySubprojects(p.id);
          const isExpanded = !!expandedProjects[p.id];
          if (displaySubs.length > 0 && isExpanded) {
            displaySubs.forEach(sub => {
              tbody.appendChild(renderRow(sub, true));
            });
          }
        });
      }
      
      table.appendChild(tbody);
      section.appendChild(table);
      container.appendChild(section);
    });
  }

  function formatStatus(status) {
    if (status === 'in_progress') return 'In Progress';
    return status.charAt(0).toUpperCase() + status.slice(1);
  }

  function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }

  function sortTable(th, colIndex) {
    const isAsc = !th.classList.contains('sort-asc');
    currentSort = { colIndex, isAsc };
    renderProjects();
  }

  async function handleFormSubmit(e) {
    e.preventDefault();
    const btn = document.getElementById('save-project-btn');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    const payload = {
      title: document.getElementById('proj-title').value,
      category: document.getElementById('proj-category').value,
      parent: document.getElementById('proj-parent').value ? parseInt(document.getElementById('proj-parent').value) : null,
      status: document.getElementById('proj-status').value,
      rank: parseInt(document.getElementById('proj-rank').value) || 0,
      start_date: document.getElementById('proj-start-date').value || null,
      end_date: document.getElementById('proj-end-date').value || null,
      description: document.getElementById('proj-desc').value
    };

    const token = localStorage.getItem('authToken');
    const csrfToken = await getCsrfToken();
    const headers = { 
      'Content-Type': 'application/json'
    };
    if (token) {
      headers['Authorization'] = 'Token ' + token;
    }
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
    }

    const url = activeProjectId ? `/api/projects/${activeProjectId}/` : '/api/projects/';
    const method = activeProjectId ? 'PATCH' : 'POST';

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to save project. Status: ' + response.status);
      }

      closeFormModal();
      loadProjects();
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Project';
    }
  }

  async function confirmDelete() {
    if (!activeProjectId) return;
    const btn = document.getElementById('delete-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Deleting...';

    const token = localStorage.getItem('authToken');
    const csrfToken = await getCsrfToken();
    const headers = {};
    if (token) {
      headers['Authorization'] = 'Token ' + token;
    }
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
    }

    try {
      const response = await fetch(`/api/projects/${activeProjectId}/`, {
        method: 'DELETE',
        headers
      });

      if (!response.ok) {
        throw new Error('Failed to delete project');
      }

      closeDeleteModal();
      loadProjects();
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Delete';
    }
  }

  loadProjects();
</script>
"""

def create_projects_page():
    print("Creating/updating Projects page...")
    projects_page, created = Page.objects.update_or_create(
        slug="projects",
        defaults={
            "title": "Projects",
            "content": projects_html,
            "is_protected": True,
            "render_as_html": True
        }
    )
    print(f"Projects page {'created' if created else 'updated'}.")

    # Let's map it to the "Ongoing Projects" menu item
    try:
        m_ongoing = MenuItem.objects.get(title="Ongoing Projects")
        m_ongoing.page = projects_page
        m_ongoing.save()
        print("Mapped Ongoing Projects menu item to the new Projects page.")
    except MenuItem.DoesNotExist:
        print("Ongoing Projects menu item does not exist. Creating it under Personal Life -> Workflow...")
        try:
            m_workflow = MenuItem.objects.get(title="Workflow")
            MenuItem.objects.get_or_create(
                title="Ongoing Projects",
                parent=m_workflow,
                defaults={'page': projects_page, 'order': 2}
            )
            print("Created Ongoing Projects menu item successfully.")
        except MenuItem.DoesNotExist:
            print("Workflow menu item not found. Creating a root-level Projects menu item...")
            MenuItem.objects.get_or_create(
                title="Projects",
                defaults={'page': projects_page, 'order': 4}
            )

if __name__ == '__main__':
    create_projects_page()
