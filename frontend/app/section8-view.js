/**
 * Section 8 views (SECTION8_MODE): Units list, the per-unit file, and the
 * Housing Authorities (PHA) directory. Everything reads and writes through
 * feature/s8-data-model's /section8/* routes (Api.s8 in api.js).
 *
 * The backend is the real boundary: every route 404s with the flag off,
 * is team-scoped, and is @require_role-gated (viewer reads, analyst
 * writes, admin backfill). The flag/role checks here are UX only -- they
 * decide which nav group and buttons to show, never what data is
 * reachable. A 403/404 from the backend still surfaces its own message.
 */
const S8_LABELS = {
    unitStatus: { occupied: 'Occupied', vacant: 'Vacant', down: 'Down', unknown: 'Unknown' },
    program: { HCV: 'HCV', PBV: 'PBV', PBRA: 'PBRA', market: 'Market' },
    propertyProgram: { HCV: 'HCV', PBV: 'PBV', PBRA: 'PBRA', mixed: 'Mixed', market: 'Market' },
    inspection: { HQS: 'HQS', 'NSPIRE-V': 'NSPIRE-V', NSPIRE: 'NSPIRE' },
    contractType: { HCV: 'HCV', PBV: 'PBV', PBRA: 'PBRA' },
    contractStatus: { active: 'Active', expired: 'Expired', terminated: 'Terminated' },
    docKind: {
        lease: 'Lease', tenancy_addendum: 'Tenancy addendum', hap_contract: 'HAP contract',
        pha_notice: 'PHA notice', inspection_report: 'Inspection report',
        payment_register: 'Payment register', rent_roll_row: 'Rent-roll row', other: 'Other',
    },
};

// escapeHtml (app.js) covers text nodes but not quotes; this one is safe
// inside a quoted attribute value too.
function s8Attr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function s8Money(value) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function s8Text(value) {
    return value === null || value === undefined || value === '' ? '—' : escapeHtml(value);
}

function s8Pill(text) {
    return `<span class="tag-chip-mini">${escapeHtml(text)}</span>`;
}

// Only http(s) links are rendered as links -- a stored "javascript:" URL
// must never become a clickable href.
function s8SafeUrl(url) {
    if (!url) return null;
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
    } catch (e) {
        return null;
    }
}

/**
 * Small form builder. A field: { key, label, type, options, required,
 * wide }. type: text | int | money | date | select | textarea | email |
 * url. Select options: [[value, label], ...] (an empty choice is added
 * unless required).
 */
function s8FormHtml(id, fields, values, submitLabel) {
    const v = values || {};
    const inputs = fields.map((f) => {
        const inputId = `${id}_${f.key}`;
        const current = v[f.key] === null || v[f.key] === undefined ? '' : v[f.key];
        const req = f.required ? 'required' : '';
        let control;
        if (f.type === 'select') {
            const opts = (f.required ? [] : [['', '—']]).concat(f.options);
            control = `<select id="${inputId}" name="${f.key}" class="text-input" ${req}>${opts.map(([val, label]) =>
                `<option value="${s8Attr(val)}" ${String(current) === String(val) ? 'selected' : ''}>${escapeHtml(label)}</option>`
            ).join('')}</select>`;
        } else if (f.type === 'textarea') {
            control = `<textarea id="${inputId}" name="${f.key}" class="text-input" rows="3" ${req}>${escapeHtml(current)}</textarea>`;
        } else {
            const type = { int: 'number', date: 'date', email: 'email', url: 'url' }[f.type] || 'text';
            const extra = f.type === 'int' ? 'step="1" min="0"' : (f.type === 'money' ? 'inputmode="decimal" placeholder="0.00"' : '');
            control = `<input id="${inputId}" name="${f.key}" type="${type}" class="text-input" value="${s8Attr(current)}" ${extra} ${req}>`;
        }
        return `<label class="s8-field${f.wide ? ' s8-field-wide' : ''}" for="${inputId}"><span>${escapeHtml(f.label)}${f.required ? ' *' : ''}</span>${control}</label>`;
    }).join('');
    return `
        <form id="${id}" class="s8-form" novalidate>
            <div class="s8-form-grid">${inputs}</div>
            <p class="access-gate-message" data-role="form-message"></p>
            <div class="s8-form-actions">
                <button type="submit" class="btn-primary">${escapeHtml(submitLabel)}</button>
                <button type="button" class="btn-secondary" data-role="form-cancel">Cancel</button>
            </div>
        </form>`;
}

/**
 * Form -> request body. Creating: blank fields are left out. Editing:
 * blank fields are sent as null so a value can be cleared. Money stays a
 * string ("1,400" is fine); the backend validates it and its 400 message
 * is shown next to the form.
 */
function s8ReadForm(form, fields, { creating }) {
    const body = {};
    fields.forEach((f) => {
        const el = form.elements[f.key];
        if (!el) return;
        const raw = el.value.trim();
        if (raw === '') {
            if (!creating) body[f.key] = null;
            return;
        }
        if (f.type === 'int' || f.intValue) {
            const n = Number(raw);
            body[f.key] = Number.isInteger(n) ? n : raw;
        } else {
            body[f.key] = raw;
        }
    });
    return body;
}

/**
 * Wires a rendered s8FormHtml: submit -> onSubmit(body), which throws on a
 * backend error; the message is shown inline. Cancel -> onCancel.
 */
function s8BindForm(container, id, fields, { creating, onSubmit, onCancel }) {
    const form = container.querySelector(`#${id}`);
    if (!form) return;
    const message = form.querySelector('[data-role="form-message"]');
    const submitBtn = form.querySelector('button[type="submit"]');
    form.querySelector('[data-role="form-cancel"]').addEventListener('click', () => onCancel && onCancel());
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        message.textContent = '';
        message.classList.remove('is-error');
        const missing = fields.find((f) => f.required && !form.elements[f.key].value.trim());
        if (missing) {
            message.textContent = `${missing.label} is required.`;
            message.classList.add('is-error');
            return;
        }
        submitBtn.disabled = true;
        try {
            await onSubmit(s8ReadForm(form, fields, { creating }));
        } catch (err) {
            message.textContent = err.message;
            message.classList.add('is-error');
        } finally {
            submitBtn.disabled = false;
        }
    });
    const first = form.querySelector('input, select, textarea');
    if (first) first.focus();
}

const S8Common = {
    _configPromise: null,

    // Cached for the page's life: the flag only changes on a redeploy.
    flagOn() {
        if (!this._configPromise) {
            this._configPromise = Api.getConfig()
                .then((cfg) => !!(cfg && cfg.section8_mode))
                .catch(() => false);
        }
        return this._configPromise;
    },

    async role() {
        try {
            const session = await Api.authSession();
            return session.authenticated ? session.role : 'viewer';
        } catch (e) {
            return 'viewer';
        }
    },

    canEdit(role) { return role === 'analyst' || role === 'admin'; },

    // A view reached by a stale link/hash with the flag off goes home.
    async guard() {
        if (await this.flagOn()) return true;
        showView('dashboard');
        return false;
    },

    phaOptions(phas) {
        return phas.map((p) => [p.id, p.short_name ? `${p.name} (${p.short_name})` : p.name]);
    },

    loading(container, text) {
        container.innerHTML = `<p class="loading-inline" role="status"><span class="spinner-small"></span> ${escapeHtml(text)}</p>`;
    },

    error(container, err) {
        container.innerHTML = `<div class="panel"><p class="error-text">${escapeHtml(err.message)}</p></div>`;
    },
};

// ------------------------------------------------------------------ Units

const S8_PROPERTY_FIELDS = (phas) => [
    { key: 'name', label: 'Property name', type: 'text', required: true },
    { key: 'address', label: 'Street address', type: 'text', wide: true },
    { key: 'program', label: 'Program', type: 'select', options: Object.entries(S8_LABELS.propertyProgram) },
    { key: 'default_pha_id', label: 'Default housing authority', type: 'select', options: S8Common.phaOptions(phas), intValue: true },
];

const S8_UNIT_FIELDS = (properties) => [
    { key: 'property_id', label: 'Property', type: 'select', required: true, options: properties.map((p) => [p.id, p.name]), intValue: true },
    { key: 'unit_label', label: 'Unit', type: 'text', required: true },
    { key: 'bedrooms', label: 'Bedrooms', type: 'int' },
    { key: 'status', label: 'Status', type: 'select', options: Object.entries(S8_LABELS.unitStatus) },
    { key: 'address', label: 'Full unit address (optional, used to match uploads)', type: 'text', wide: true },
];

const S8UnitsView = {
    role: 'viewer',
    _loadToken: 0,
    units: [],
    properties: [],
    phas: [],
    tenancyByUnit: {},
    propertyFilter: '',

    async load() {
        if (!(await S8Common.guard())) return;
        const content = document.getElementById('s8UnitsContent');
        const token = ++this._loadToken;
        S8Common.loading(content, 'Loading units...');
        try {
            const [role, units, tenancies, properties, phas] = await Promise.all([
                S8Common.role(),
                Api.s8.units.list(),
                Api.s8.tenancies.list({ status: 'current' }),
                Api.s8.properties.list(),
                Api.s8.phas.list(),
            ]);
            if (token !== this._loadToken) return; // a newer load() won the race
            this.role = role;
            this.units = units;
            this.properties = properties;
            this.phas = phas;
            this.tenancyByUnit = {};
            tenancies.forEach((t) => { this.tenancyByUnit[t.unit_id] = t; });
            if (this.propertyFilter && !properties.some((p) => String(p.id) === this.propertyFilter)) this.propertyFilter = '';
            this.renderActions();
            this.render();
        } catch (err) {
            if (token !== this._loadToken) return;
            document.getElementById('s8UnitsActions').innerHTML = '';
            S8Common.error(content, err);
        }
    },

    renderActions() {
        const bar = document.getElementById('s8UnitsActions');
        const buttons = [];
        if (this.role === 'admin') buttons.push('<button type="button" class="btn-secondary" data-action="backfill">Group uploads into units</button>');
        if (S8Common.canEdit(this.role)) {
            buttons.push('<button type="button" class="btn-secondary" data-action="add-property">Add property</button>');
            if (this.properties.length) buttons.push('<button type="button" class="btn-primary" data-action="add-unit">Add unit</button>');
        }
        bar.innerHTML = buttons.join('');
        bar.querySelectorAll('[data-action]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                if (action === 'backfill') this.backfill();
                else if (action === 'add-property') this.showForm('property');
                else if (action === 'add-unit') this.showForm('unit');
            });
        });
    },

    render() {
        const content = document.getElementById('s8UnitsContent');
        if (!this.units.length && !this.properties.length) {
            content.innerHTML = `
                <div class="s8-form-slot" id="s8UnitsFormSlot"></div>
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
                    </div>
                    <p class="empty-state-title">No units yet</p>
                    <p class="empty-state-hint">${S8Common.canEdit(this.role)
                        ? 'Add a property and its units by hand, or (admins) use “Group uploads into units” to build them from the leases and rent rolls you have already uploaded.'
                        : 'An analyst or admin on your team can add properties and units.'}</p>
                </div>`;
            return;
        }

        const propertyById = {};
        this.properties.forEach((p) => { propertyById[p.id] = p; });
        const phaById = {};
        this.phas.forEach((p) => { phaById[p.id] = p; });

        const groups = this.properties.map((p) => ({ property: p, units: [] }));
        const groupById = {};
        groups.forEach((g) => { groupById[g.property.id] = g; });
        const orphan = { property: null, units: [] };
        this.units.forEach((u) => { (groupById[u.property_id] || orphan).units.push(u); });
        if (orphan.units.length) groups.push(orphan);
        const shown = this.propertyFilter ? groups.filter((g) => g.property && String(g.property.id) === this.propertyFilter) : groups;

        const filter = this.properties.length > 1 ? `
            <div class="s8-toolbar">
                <label class="s8-inline-label" for="s8PropertyFilter">Property</label>
                <select id="s8PropertyFilter" class="text-input">
                    <option value="">All properties (${this.properties.length})</option>
                    ${this.properties.map((p) => `<option value="${p.id}" ${String(p.id) === this.propertyFilter ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('')}
                </select>
            </div>` : '';

        content.innerHTML = `
            <div class="s8-form-slot" id="s8UnitsFormSlot"></div>
            ${filter}
            ${shown.map((g) => this.groupHtml(g, phaById)).join('')}`;

        const filterEl = document.getElementById('s8PropertyFilter');
        if (filterEl) filterEl.addEventListener('change', () => { this.propertyFilter = filterEl.value; this.render(); });
        content.querySelectorAll('tr[data-unit-id]').forEach((row) => {
            const open = () => showView('s8unit', { unitId: parseInt(row.dataset.unitId, 10) });
            row.addEventListener('click', open);
            row.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
        });
    },

    groupHtml(group, phaById) {
        const p = group.property;
        const title = p ? escapeHtml(p.name) : 'Other units';
        const meta = p ? [p.address, p.program ? S8_LABELS.propertyProgram[p.program] : null].filter(Boolean).map(escapeHtml).join(' · ') : '';
        const rows = group.units.map((u) => {
            const t = this.tenancyByUnit[u.id];
            const pha = t && t.pha_id ? phaById[t.pha_id] : null;
            return `
                <tr data-unit-id="${u.id}" tabindex="0" aria-label="Open unit ${s8Attr(u.unit_label)}">
                    <td><strong>${escapeHtml(u.unit_label)}</strong></td>
                    <td>${s8Text(u.bedrooms)}</td>
                    <td>${s8Pill(S8_LABELS.unitStatus[u.status] || 'Unknown')}</td>
                    <td>${t ? s8Text(t.head_of_household) : '<span class="muted">No current tenancy</span>'}</td>
                    <td>${pha ? escapeHtml(pha.short_name || pha.name) : '—'}</td>
                    <td>${t && t.program ? escapeHtml(S8_LABELS.program[t.program] || t.program) : '—'}</td>
                    <td class="s8-num">${t ? s8Money(t.contract_rent) : '—'}</td>
                    <td class="s8-num">${t ? s8Money(t.tenant_rent) : '—'}</td>
                    <td class="s8-num">${t ? s8Money(t.hap) : '—'}</td>
                </tr>`;
        }).join('');
        return `
            <div class="panel">
                <div class="panel-header">
                    <div>
                        <h2>${title}</h2>
                        ${meta ? `<p class="s8-subtle">${meta}</p>` : ''}
                    </div>
                    <span class="s8-subtle">${group.units.length} ${group.units.length === 1 ? 'unit' : 'units'}</span>
                </div>
                ${group.units.length ? `
                <div class="table-scroll s8-table-scroll">
                    <table class="data-table s8-table">
                        <thead><tr>
                            <th>Unit</th><th>Beds</th><th>Status</th><th>Household</th><th>PHA</th><th>Program</th>
                            <th class="s8-num">Contract rent</th><th class="s8-num">Tenant share</th><th class="s8-num">HAP</th>
                        </tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>` : '<p class="empty-inline">No units in this property yet.</p>'}
            </div>`;
    },

    showForm(kind) {
        const slot = document.getElementById('s8UnitsFormSlot');
        if (!slot) return;
        const isProperty = kind === 'property';
        const fields = isProperty ? S8_PROPERTY_FIELDS(this.phas) : S8_UNIT_FIELDS(this.properties);
        const defaults = isProperty ? {} : { property_id: this.propertyFilter || (this.properties[0] && this.properties[0].id), status: 'occupied' };
        slot.innerHTML = `
            <div class="panel">
                <div class="panel-header"><h2>${isProperty ? 'Add property' : 'Add unit'}</h2></div>
                ${s8FormHtml('s8UnitsForm', fields, defaults, isProperty ? 'Add property' : 'Add unit')}
            </div>`;
        s8BindForm(slot, 's8UnitsForm', fields, {
            creating: true,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                if (isProperty) {
                    const created = await Api.s8.properties.create(body);
                    showToast(`${created.name} added.`, 'success');
                } else {
                    const created = await Api.s8.units.create(body);
                    showToast(`Unit ${created.unit_label} added.`, 'success');
                }
                await this.load();
            },
        });
        slot.scrollIntoView({ block: 'nearest' });
    },

    async backfill() {
        let preview;
        try {
            preview = await Api.s8.backfill(false);
        } catch (err) {
            showError(err.message);
            return;
        }
        const props = preview.properties_to_create.length;
        const units = preview.units_to_create.length;
        const links = preview.links_to_create;
        const skipped = preview.skipped.length;
        const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
        if (!props && !units && !links) {
            showToast(skipped
                ? `Nothing to group. ${plural(skipped, 'upload was', 'uploads were')} skipped: no property address.`
                : 'Nothing to group: every upload is already linked to a unit.', 'info');
            return;
        }
        const message = `Will create ${plural(props, 'property', 'properties')} and ${plural(units, 'unit', 'units')}, and link ${plural(links, 'document', 'documents')}.`
            + (skipped ? ` ${plural(skipped, 'upload', 'uploads')} skipped: no property address.` : '')
            + ' New units start with status “Unknown”. Your uploads themselves are not changed.';
        const ok = await confirmDialog({ title: 'Group uploads into units?', message, confirmText: 'Apply' });
        if (!ok) return;
        try {
            const result = await Api.s8.backfill(true);
            const c = result.created || {};
            showToast(`Created ${plural(c.properties || 0, 'property', 'properties')}, ${plural(c.units || 0, 'unit', 'units')} and ${plural(c.links || 0, 'document link', 'document links')}.`, 'success');
            await this.load();
        } catch (err) {
            showError(err.message);
        }
    },
};

// -------------------------------------------------------------- Unit file

const S8_TENANCY_FIELDS = (phas) => [
    { key: 'head_of_household', label: 'Head of household', type: 'text' },
    { key: 'household_size', label: 'Household size', type: 'int' },
    { key: 'pha_id', label: 'Housing authority', type: 'select', options: S8Common.phaOptions(phas), intValue: true },
    { key: 'program', label: 'Program', type: 'select', options: Object.entries(S8_LABELS.program) },
    { key: 'voucher_bedrooms', label: 'Voucher bedrooms', type: 'int' },
    { key: 'move_in_date', label: 'Move-in date', type: 'date' },
    { key: 'contract_rent', label: 'Contract rent ($/mo)', type: 'money' },
    { key: 'tenant_rent', label: 'Tenant share ($/mo)', type: 'money' },
    { key: 'hap', label: 'HAP ($/mo)', type: 'money' },
    { key: 'utility_allowance', label: 'Utility allowance ($/mo)', type: 'money' },
    { key: 'amounts_effective_date', label: 'Amounts effective', type: 'date' },
];

const S8_HAP_FIELDS = (phas) => [
    { key: 'contract_type', label: 'Type', type: 'select', required: true, options: Object.entries(S8_LABELS.contractType) },
    { key: 'contract_number', label: 'Contract number', type: 'text' },
    { key: 'form', label: 'HUD form', type: 'text' },
    { key: 'pha_id', label: 'Housing authority', type: 'select', options: S8Common.phaOptions(phas), intValue: true },
    { key: 'start_date', label: 'Start date', type: 'date' },
    { key: 'end_date', label: 'End date', type: 'date' },
    { key: 'contract_rent', label: 'Contract rent ($/mo)', type: 'money' },
    { key: 'initial_hap', label: 'Initial HAP ($/mo)', type: 'money' },
    { key: 'status', label: 'Status', type: 'select', options: Object.entries(S8_LABELS.contractStatus) },
];

const S8_UNIT_EDIT_FIELDS = [
    { key: 'bedrooms', label: 'Bedrooms', type: 'int' },
    { key: 'status', label: 'Status', type: 'select', required: true, options: Object.entries(S8_LABELS.unitStatus) },
];

// Cents comparison so "1400.10" + "0.20" never looks off by float noise.
function s8SplitMismatch(t) {
    if (!t || t.contract_rent === null || t.tenant_rent === null || t.hap === null) return false;
    const cents = (v) => Math.round(Number(v) * 100);
    return cents(t.tenant_rent) + cents(t.hap) !== cents(t.contract_rent);
}

const S8UnitFileView = {
    role: 'viewer',
    unitId: null,
    unit: null,
    property: null,
    phas: [],
    pastTenancies: [],
    _loadToken: 0,

    async load(params) {
        if (!(await S8Common.guard())) return;
        const unitId = params && params.unitId ? params.unitId : this.unitId;
        if (!unitId) { showView('s8units'); return; }
        this.unitId = unitId;
        const token = ++this._loadToken;
        const content = document.getElementById('s8UnitContent');
        S8Common.loading(content, 'Loading unit file...');
        try {
            const [role, unit, phas, past] = await Promise.all([
                S8Common.role(),
                Api.s8.units.get(unitId),
                Api.s8.phas.list(),
                Api.s8.tenancies.list({ unit_id: unitId, status: 'past' }),
            ]);
            const property = await Api.s8.properties.get(unit.property_id).catch(() => null);
            if (token !== this._loadToken) return; // a newer load() won the race
            Object.assign(this, { role, unit, phas, property, pastTenancies: past });
            this.render();
        } catch (err) {
            if (token !== this._loadToken) return;
            content.innerHTML = `<button type="button" class="btn-text s8-back" data-action="back">← Units</button>`;
            content.insertAdjacentHTML('beforeend', `<div class="panel"><p class="error-text">${escapeHtml(err.message)}</p></div>`);
            content.querySelector('[data-action="back"]').addEventListener('click', () => showView('s8units'));
        }
    },

    // After a save, re-render only if the user is still looking at the same
    // unit -- otherwise a slow save would paint the old unit over the new one.
    async reloadIfOpen(unitId) {
        if (currentViewName === 's8unit' && this.unitId === unitId) await this.load({ unitId });
    },

    phaName(id) {
        const p = this.phas.find((x) => x.id === id);
        return p ? (p.short_name || p.name) : null;
    },

    render() {
        const u = this.unit;
        const canEdit = S8Common.canEdit(this.role);
        const content = document.getElementById('s8UnitContent');
        const subtitle = [
            this.property ? escapeHtml(this.property.name) : null,
            u.bedrooms === null || u.bedrooms === undefined ? null : `${escapeHtml(u.bedrooms)} bed`,
        ].filter(Boolean).join(' · ');
        content.innerHTML = `
            <button type="button" class="btn-text s8-back" data-action="back">← Units</button>
            <div class="view-header">
                <div>
                    <h1>Unit ${escapeHtml(u.unit_label)} ${s8Pill(S8_LABELS.unitStatus[u.status] || 'Unknown')}</h1>
                    <p class="view-subtitle">${subtitle || '&nbsp;'}</p>
                </div>
                <div class="view-header-actions">
                    ${canEdit ? '<button type="button" class="btn-secondary" data-action="edit-unit">Edit unit</button>' : ''}
                </div>
            </div>
            <div id="s8UnitEditSlot"></div>
            <div class="s8-unit-grid">
                ${this.tenancyPanelHtml(canEdit)}
                ${this.hapPanelHtml(canEdit)}
                ${this.documentsPanelHtml(canEdit)}
                ${this.pastPanelHtml()}
            </div>`;
        this.bind(content);
    },

    tenancyPanelHtml(canEdit) {
        const t = this.unit.current_tenancy;
        const actions = canEdit ? `
            <div class="s8-panel-actions">
                ${t ? '<button type="button" class="btn-secondary" data-action="edit-tenancy">Edit</button>' : ''}
                <button type="button" class="btn-${t ? 'secondary' : 'primary'}" data-action="new-tenancy">Record new tenancy</button>
            </div>` : '';
        let body;
        if (!t) {
            body = '<p class="empty-inline">No current tenancy recorded.</p>';
        } else {
            const rows = [
                ['Household', s8Text(t.head_of_household)],
                ['Household size', s8Text(t.household_size)],
                ['Housing authority', s8Text(this.phaName(t.pha_id))],
                ['Program', s8Text(t.program && (S8_LABELS.program[t.program] || t.program))],
                ['Voucher bedrooms', s8Text(t.voucher_bedrooms)],
                ['Move-in', s8Text(t.move_in_date)],
                ['Contract rent', s8Money(t.contract_rent)],
                ['Tenant share', s8Money(t.tenant_rent)],
                ['HAP', s8Money(t.hap)],
                ['Utility allowance', s8Money(t.utility_allowance)],
                ['Amounts effective', s8Text(t.amounts_effective_date)],
            ];
            body = `
                <dl class="s8-dl">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>
                ${s8SplitMismatch(t) ? '<p class="s8-note">Tenant share + HAP doesn’t equal contract rent.</p>' : ''}`;
        }
        return `
            <div class="panel s8-panel-wide">
                <div class="panel-header"><h2>Current tenancy</h2>${actions}</div>
                <div id="s8TenancySlot"></div>
                ${body}
            </div>`;
    },

    hapPanelHtml(canEdit) {
        const contracts = this.unit.hap_contracts || [];
        const rows = contracts.map((c) => `
            <tr>
                <td>${escapeHtml(S8_LABELS.contractType[c.contract_type] || c.contract_type)}</td>
                <td>${s8Text(c.contract_number)}</td>
                <td>${s8Text(c.form)}</td>
                <td>${s8Text(this.phaName(c.pha_id))}</td>
                <td>${c.start_date || c.end_date ? `${s8Text(c.start_date)} – ${s8Text(c.end_date)}` : '—'}</td>
                <td class="s8-num">${s8Money(c.contract_rent)}</td>
                <td class="s8-num">${s8Money(c.initial_hap)}</td>
                <td>${s8Pill(S8_LABELS.contractStatus[c.status] || c.status)}</td>
            </tr>`).join('');
        return `
            <div class="panel s8-panel-wide">
                <div class="panel-header"><h2>HAP contracts</h2>
                    ${canEdit ? '<div class="s8-panel-actions"><button type="button" class="btn-secondary" data-action="add-hap">Add HAP contract</button></div>' : ''}
                </div>
                <div id="s8HapSlot"></div>
                ${contracts.length ? `
                <div class="table-scroll s8-table-scroll">
                    <table class="team-members-table s8-table">
                        <thead><tr><th>Type</th><th>Number</th><th>Form</th><th>PHA</th><th>Term</th><th class="s8-num">Contract rent</th><th class="s8-num">Initial HAP</th><th>Status</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>` : '<p class="empty-inline">No HAP contracts recorded.</p>'}
            </div>`;
    },

    documentsPanelHtml(canEdit) {
        const docs = this.unit.documents || [];
        const kindOptions = Object.entries(S8_LABELS.docKind);
        const rows = docs.map((d) => `
            <tr data-link-id="${d.id}">
                <td><button type="button" class="btn-text s8-doc-link" data-lease-id="${d.lease_id}">${escapeHtml(d.display_name || d.filename || `Document ${d.lease_id}`)}</button></td>
                <td>${canEdit
                    ? `<select class="text-input s8-kind-select" data-link-id="${d.id}" aria-label="Document kind">${kindOptions.map(([v, l]) => `<option value="${v}" ${d.doc_kind === v ? 'selected' : ''}>${escapeHtml(l)}</option>`).join('')}</select>`
                    : s8Pill(S8_LABELS.docKind[d.doc_kind] || d.doc_kind)}</td>
                <td>${d.linked_by === 'backfill' ? 'Grouped automatically' : 'Linked by hand'}</td>
                ${canEdit ? `<td><button type="button" class="btn-text" data-action="unlink" data-link-id="${d.id}">Unlink</button></td>` : ''}
            </tr>`).join('');
        return `
            <div class="panel s8-panel-wide">
                <div class="panel-header"><h2>Documents</h2>
                    ${canEdit ? '<div class="s8-panel-actions"><button type="button" class="btn-secondary" data-action="link-doc">Link a document</button></div>' : ''}
                </div>
                <div id="s8DocSlot"></div>
                ${docs.length ? `
                <div class="table-scroll s8-table-scroll">
                    <table class="team-members-table s8-table">
                        <thead><tr><th>Document</th><th>Kind</th><th>Source</th>${canEdit ? '<th></th>' : ''}</tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>` : '<p class="empty-inline">No documents linked to this unit.</p>'}
            </div>`;
    },

    pastPanelHtml() {
        const past = this.pastTenancies;
        if (!past.length) return '';
        const rows = past.map((t) => `
            <tr>
                <td>${s8Text(t.head_of_household)}</td>
                <td>${s8Text(t.program && (S8_LABELS.program[t.program] || t.program))}</td>
                <td>${s8Text(this.phaName(t.pha_id))}</td>
                <td>${s8Text(t.move_in_date)} – ${s8Text(t.move_out_date)}</td>
                <td class="s8-num">${s8Money(t.contract_rent)}</td>
                <td class="s8-num">${s8Money(t.tenant_rent)}</td>
                <td class="s8-num">${s8Money(t.hap)}</td>
            </tr>`).join('');
        return `
            <details class="panel s8-panel-wide s8-past">
                <summary><h2>Past tenancies (${past.length})</h2></summary>
                <div class="table-scroll s8-table-scroll">
                    <table class="team-members-table s8-table">
                        <thead><tr><th>Household</th><th>Program</th><th>PHA</th><th>Dates</th><th class="s8-num">Contract rent</th><th class="s8-num">Tenant share</th><th class="s8-num">HAP</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </details>`;
    },

    bind(content) {
        const unitId = this.unit.id;
        const on = (action, fn) => content.querySelectorAll(`[data-action="${action}"]`).forEach((el) => el.addEventListener('click', () => fn(el)));
        on('back', () => showView('s8units'));
        on('edit-unit', () => this.editUnit());
        on('edit-tenancy', () => this.tenancyForm(false));
        on('new-tenancy', () => this.tenancyForm(true));
        on('add-hap', () => this.hapForm());
        on('link-doc', () => this.linkForm());
        on('unlink', (el) => this.unlink(parseInt(el.dataset.linkId, 10)));
        content.querySelectorAll('.s8-doc-link').forEach((btn) => {
            btn.addEventListener('click', () => showLeaseDetail(parseInt(btn.dataset.leaseId, 10)));
        });
        content.querySelectorAll('.s8-kind-select').forEach((sel) => {
            sel.addEventListener('change', async () => {
                try {
                    await Api.s8.updateUnitDocument(parseInt(sel.dataset.linkId, 10), { doc_kind: sel.value });
                    showToast('Document kind updated.', 'success');
                } catch (err) {
                    showError(err.message);
                }
                await this.reloadIfOpen(unitId);
            });
        });
    },

    editUnit() {
        const unitId = this.unit.id;
        const slot = document.getElementById('s8UnitEditSlot');
        slot.innerHTML = `<div class="panel"><div class="panel-header"><h2>Edit unit</h2></div>${s8FormHtml('s8UnitEditForm', S8_UNIT_EDIT_FIELDS, this.unit, 'Save')}</div>`;
        s8BindForm(slot, 's8UnitEditForm', S8_UNIT_EDIT_FIELDS, {
            creating: false,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                await Api.s8.units.update(this.unit.id, body);
                showToast('Unit updated.', 'success');
                await this.reloadIfOpen(unitId);
            },
        });
    },

    tenancyForm(isNew) {
        const unitId = this.unit.id;
        const slot = document.getElementById('s8TenancySlot');
        const fields = S8_TENANCY_FIELDS(this.phas);
        const current = this.unit.current_tenancy;
        const defaults = isNew ? { pha_id: this.property && this.property.default_pha_id } : current;
        slot.innerHTML = `<div class="s8-inline-form"><h3>${isNew ? 'Record new tenancy' : 'Edit current tenancy'}</h3>${s8FormHtml('s8TenancyForm', fields, defaults, isNew ? 'Record tenancy' : 'Save')}</div>`;
        s8BindForm(slot, 's8TenancyForm', fields, {
            creating: isNew,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                if (!isNew) {
                    await Api.s8.tenancies.update(current.id, body);
                    showToast('Tenancy updated.', 'success');
                } else {
                    if (current) {
                        const name = current.head_of_household || 'the current household';
                        const ok = await confirmDialog({
                            title: 'Replace the current tenancy?',
                            message: `This marks ${name}'s tenancy as past (move-out = the new move-in date) and makes this one current.`,
                            confirmText: 'Record tenancy',
                        });
                        if (!ok) return;
                    }
                    await Api.s8.tenancies.create({ ...body, unit_id: this.unit.id, end_current: !!current });
                    showToast('Tenancy recorded.', 'success');
                }
                await this.reloadIfOpen(unitId);
            },
        });
    },

    hapForm() {
        const unitId = this.unit.id;
        const slot = document.getElementById('s8HapSlot');
        const fields = S8_HAP_FIELDS(this.phas);
        const t = this.unit.current_tenancy;
        const defaults = {
            contract_type: t && t.program && S8_LABELS.contractType[t.program] ? t.program : 'HCV',
            pha_id: (t && t.pha_id) || (this.property && this.property.default_pha_id),
            contract_rent: t ? t.contract_rent : null,
            status: 'active',
        };
        slot.innerHTML = `<div class="s8-inline-form"><h3>Add HAP contract</h3>${s8FormHtml('s8HapForm', fields, defaults, 'Add contract')}</div>`;
        s8BindForm(slot, 's8HapForm', fields, {
            creating: true,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                await Api.s8.hapContracts.create({ ...body, unit_id: this.unit.id, property_id: this.unit.property_id });
                showToast('HAP contract added.', 'success');
                await this.reloadIfOpen(unitId);
            },
        });
    },

    async linkForm() {
        const unitId = this.unit.id;
        const slot = document.getElementById('s8DocSlot');
        slot.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading your uploads...</p>';
        let leases;
        try {
            leases = await Api.listLeases();
        } catch (err) {
            slot.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
            return;
        }
        const linked = new Set((this.unit.documents || []).map((d) => d.lease_id));
        const available = leases.filter((l) => !linked.has(l.id));
        if (!available.length) {
            slot.innerHTML = '<p class="empty-inline">Every upload is already linked to this unit. Upload a document first, then link it here.</p>';
            return;
        }
        const tenancies = [this.unit.current_tenancy, ...this.pastTenancies].filter(Boolean);
        const fields = [
            { key: 'lease_id', label: 'Upload', type: 'select', required: true, wide: true, intValue: true, options: available.map((l) => [l.id, l.display_name || l.filename]) },
            { key: 'doc_kind', label: 'Kind', type: 'select', required: true, options: Object.entries(S8_LABELS.docKind) },
            { key: 'tenancy_id', label: 'Tenancy (optional)', type: 'select', intValue: true, options: tenancies.map((t) => [t.id, `${t.head_of_household || 'Household'} (${t.status})`]) },
        ];
        slot.innerHTML = `<div class="s8-inline-form"><h3>Link a document</h3>${s8FormHtml('s8LinkForm', fields, { doc_kind: 'lease' }, 'Link document')}</div>`;
        s8BindForm(slot, 's8LinkForm', fields, {
            creating: true,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                await Api.s8.linkUnitDocument(this.unit.id, body);
                showToast('Document linked.', 'success');
                await this.reloadIfOpen(unitId);
            },
        });
    },

    async unlink(linkId) {
        const unitId = this.unit.id;
        const ok = await confirmDialog({
            title: 'Unlink this document?',
            message: 'It stays in your uploads; it just won’t show in this unit file.',
            confirmText: 'Unlink',
        });
        if (!ok) return;
        try {
            await Api.s8.updateUnitDocument(linkId, { archived: true });
            showToast('Document unlinked.', 'success');
        } catch (err) {
            showError(err.message);
        }
        await this.reloadIfOpen(unitId);
    },
};

// ---------------------------------------------------- Housing Authorities

const S8_PHA_FIELDS = [
    { key: 'name', label: 'Name', type: 'text', required: true, wide: true },
    { key: 'short_name', label: 'Short name', type: 'text' },
    { key: 'jurisdiction', label: 'Jurisdiction', type: 'text' },
    { key: 'inspection_standard', label: 'Inspection standard', type: 'select', options: Object.entries(S8_LABELS.inspection) },
    { key: 'payment_day', label: 'HAP payment day (1–31)', type: 'int' },
    { key: 'rent_increase_notice_days', label: 'Rent-increase notice (days)', type: 'int' },
    { key: 'portal_url', label: 'Portal link', type: 'url', wide: true },
    { key: 'contact_name', label: 'Caseworker / contact', type: 'text' },
    { key: 'contact_email', label: 'Contact email', type: 'email' },
    { key: 'contact_phone', label: 'Contact phone', type: 'text' },
    { key: 'notes', label: 'Notes', type: 'textarea', wide: true },
];

const S8PhasView = {
    role: 'viewer',
    _loadToken: 0,
    phas: [],
    showArchived: false,

    async load() {
        if (!(await S8Common.guard())) return;
        const content = document.getElementById('s8PhasContent');
        const token = ++this._loadToken;
        S8Common.loading(content, 'Loading housing authorities...');
        try {
            const [role, phas] = await Promise.all([
                S8Common.role(),
                Api.s8.phas.list(this.showArchived ? { include_archived: 'true' } : {}),
            ]);
            if (token !== this._loadToken) return; // a newer load() won the race
            this.role = role;
            this.phas = phas;
            this.renderActions();
            this.render();
        } catch (err) {
            if (token !== this._loadToken) return;
            document.getElementById('s8PhasActions').innerHTML = '';
            S8Common.error(content, err);
        }
    },

    renderActions() {
        const bar = document.getElementById('s8PhasActions');
        bar.innerHTML = S8Common.canEdit(this.role) ? '<button type="button" class="btn-primary" data-action="add-pha">Add housing authority</button>' : '';
        const btn = bar.querySelector('[data-action="add-pha"]');
        if (btn) btn.addEventListener('click', () => this.showForm(null));
    },

    render() {
        const content = document.getElementById('s8PhasContent');
        const canEdit = S8Common.canEdit(this.role);
        const toggle = canEdit ? `
            <label class="checkbox-label s8-toolbar"><input type="checkbox" id="s8ShowArchivedPhas" ${this.showArchived ? 'checked' : ''}> Show archived</label>` : '';
        let body;
        if (!this.phas.length) {
            body = `<div class="empty-state">
                <p class="empty-state-title">No housing authorities yet</p>
                <p class="empty-state-hint">${canEdit ? 'Add the PHAs you work with. Their payment day, notice period and inspection standard drive the deadlines later features track.' : 'An analyst or admin on your team can add housing authorities.'}</p>
            </div>`;
        } else {
            const rows = this.phas.map((p) => {
                const portal = s8SafeUrl(p.portal_url);
                const contact = [p.contact_name, p.contact_email, p.contact_phone].filter(Boolean).map(escapeHtml).join('<br>');
                return `
                    <tr class="${p.archived ? 'status-pill-deactivated' : ''}">
                        <td><strong>${escapeHtml(p.name)}</strong>${p.short_name ? `<br><span class="s8-subtle">${escapeHtml(p.short_name)}</span>` : ''}${p.archived ? ` ${s8Pill('Archived')}` : ''}</td>
                        <td>${s8Text(p.jurisdiction)}</td>
                        <td>${s8Text(p.inspection_standard)}</td>
                        <td>${s8Text(p.payment_day)}</td>
                        <td>${p.rent_increase_notice_days === null || p.rent_increase_notice_days === undefined ? '—' : `${escapeHtml(p.rent_increase_notice_days)} days`}</td>
                        <td>${contact || '—'}</td>
                        <td>${portal ? `<a href="${s8Attr(portal)}" target="_blank" rel="noopener noreferrer">Open</a>` : '—'}</td>
                        ${canEdit ? `<td><span class="s8-row-actions">
                            <button type="button" class="btn-text" data-action="edit" data-pha-id="${p.id}">Edit</button>
                            <button type="button" class="btn-text" data-action="${p.archived ? 'restore' : 'archive'}" data-pha-id="${p.id}">${p.archived ? 'Restore' : 'Archive'}</button>
                        </span></td>` : ''}
                    </tr>`;
            }).join('');
            body = `
                <div class="panel">
                    <div class="table-scroll s8-table-scroll">
                        <table class="team-members-table s8-table s8-table-wrap">
                            <thead><tr><th>Name</th><th>Jurisdiction</th><th>Inspections</th><th>HAP pay day</th><th>Rent-increase notice</th><th>Contact</th><th>Portal</th>${canEdit ? '<th></th>' : ''}</tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                </div>`;
        }
        content.innerHTML = `<div id="s8PhaFormSlot"></div>${toggle}${body}`;

        const toggleEl = document.getElementById('s8ShowArchivedPhas');
        if (toggleEl) toggleEl.addEventListener('change', () => { this.showArchived = toggleEl.checked; this.load(); });
        content.querySelectorAll('[data-action="edit"]').forEach((btn) => {
            btn.addEventListener('click', () => this.showForm(this.phas.find((p) => p.id === parseInt(btn.dataset.phaId, 10))));
        });
        content.querySelectorAll('[data-action="archive"], [data-action="restore"]').forEach((btn) => {
            btn.addEventListener('click', () => this.setArchived(parseInt(btn.dataset.phaId, 10), btn.dataset.action === 'archive'));
        });
    },

    showForm(pha) {
        const slot = document.getElementById('s8PhaFormSlot');
        const editing = !!pha;
        slot.innerHTML = `
            <div class="panel">
                <div class="panel-header"><h2>${editing ? `Edit ${escapeHtml(pha.name)}` : 'Add housing authority'}</h2></div>
                ${s8FormHtml('s8PhaForm', S8_PHA_FIELDS, pha || {}, editing ? 'Save' : 'Add housing authority')}
            </div>`;
        s8BindForm(slot, 's8PhaForm', S8_PHA_FIELDS, {
            creating: !editing,
            onCancel: () => { slot.innerHTML = ''; },
            onSubmit: async (body) => {
                if (editing) {
                    await Api.s8.phas.update(pha.id, body);
                    showToast('Housing authority updated.', 'success');
                } else {
                    const created = await Api.s8.phas.create(body);
                    showToast(`${created.name} added.`, 'success');
                }
                await this.load();
            },
        });
        slot.scrollIntoView({ block: 'nearest' });
    },

    async setArchived(phaId, archived) {
        if (archived && !(await confirmDialog({
            title: 'Archive this housing authority?',
            message: 'It disappears from lists and pickers. Tenancies and contracts that reference it keep it. You can restore it from “Show archived”.',
            confirmText: 'Archive',
        }))) return;
        try {
            await Api.s8.phas.update(phaId, { archived });
            showToast(archived ? 'Archived.' : 'Restored.', 'success');
        } catch (err) {
            showError(err.message);
        }
        await this.load();
    },
};

registerView('s8units', S8UnitsView);
registerView('s8unit', S8UnitFileView);
registerView('s8phas', S8PhasView);

// Reveal the nav group only when the backend says the flag is on.
S8Common.flagOn().then((on) => {
    const group = document.getElementById('section8NavGroup');
    if (group && on) group.hidden = false;
});
