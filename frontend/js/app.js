'use strict';

const byId = (id) => document.getElementById(id);
const textInput = byId('claim-text');
const urlInput = byId('claim-url');
const accountDialog = byId('account-dialog');
const historyDialog = byId('history-dialog');
const shareDialog = byId('share-dialog');
const verdictLabels = { REAL: 'Supported', FALSE: 'False', MISLEADING: 'Misleading', UNVERIFIED: 'Unverified' };
const stanceLabels = { SUPPORT: 'Supports claim', CONTRADICT: 'Contradicts claim', NEUTRAL: 'Provides context' };
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });
let mode = 'text';
let report;
let token = sessionStorage.getItem('verifynews-token');
let user;
let accountMode;
let historyPage = 1;
let historyRequest = 0;
let noticeTimer;

function element(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
}

function message(id, value = '') {
    const node = byId(id);
    node.textContent = value;
    node.hidden = !value;
}

function notify(value) {
    clearTimeout(noticeTimer);
    message('notice', value);
    noticeTimer = setTimeout(() => message('notice'), 3200);
}

function setSession(accessToken, profile) {
    token = accessToken;
    user = profile;
    if (token) sessionStorage.setItem('verifynews-token', token);
    else sessionStorage.removeItem('verifynews-token');
    byId('account-button-label').textContent = user ? 'Account' : 'Sign in';
}

async function api(path, { method = 'GET', body, authenticated = true, timeoutMs } = {}) {
    const requestToken = authenticated ? token : null;
    const headers = { Accept: 'application/json' };
    if (requestToken) headers.Authorization = 'Bearer ' + requestToken;
    if (body) headers['Content-Type'] = 'application/json';
    const controller = new AbortController();
    const effectiveTimeout = timeoutMs ?? (path === '/verify' ? 65000 : 15000);
    const timer = setTimeout(() => controller.abort(), effectiveTimeout);
    let response;
    try {
        response = await fetch('/api/v1' + path, {
            method,
            headers,
            body: body && JSON.stringify(body),
            signal: controller.signal
        });
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('The request timed out. Please try again.');
        }
        throw new Error('Network error. Check your connection and try again.');
    } finally {
        clearTimeout(timer);
    }
    if (response.status === 204) return;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (response.status === 401 && requestToken && token === requestToken) setSession(null, null);
        const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
        throw new Error(data.message || detail || 'Request failed. Please try again.');
    }
    return data;
}

function selectMode(value) {
    mode = value;
    const isText = mode === 'text';
    byId('mode-text').setAttribute('aria-pressed', isText);
    byId('mode-url').setAttribute('aria-pressed', !isText);
    byId('text-field').hidden = !isText;
    byId('url-field').hidden = isText;
    message('verify-error');
    (isText ? textInput : urlInput).focus();
}

function updateCount() {
    byId('text-count').textContent = textInput.value.length.toLocaleString() + ' / ' + textInput.maxLength.toLocaleString() + ' characters';
}

function publicWebUrl(value) {
    try {
        const url = new URL(value);
        if (['https:', 'http:'].includes(url.protocol) && !url.username && !url.password) return url.href;
    } catch {
        return null;
    }
    return null;
}

function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : dateFormat.format(date);
}

function badge(kind, label) {
    const node = element('span', label, 'badge');
    node.dataset.kind = kind;
    return node;
}

function renderReport(data) {
    report = data;
    const verdict = byId('verdict');
    verdict.dataset.kind = data.verdict;
    verdict.textContent = verdictLabels[data.verdict] || data.verdict;
    byId('confidence').textContent = data.confidence + '% verification confidence';
    byId('report-claim').textContent = data.claim.primary_claim;
    message('entities', data.claim.entities?.length ? 'Mentioned: ' + data.claim.entities.join(', ') : '');
    byId('explanation').textContent = data.explanation || data.summary;
    const evidence = data.evidence_summary;
    byId('evidence-counts').replaceChildren(
        element('li', evidence.supporting + ' supporting'),
        element('li', evidence.contradicting + ' contradicting'),
        element('li', evidence.neutral + ' for context')
    );
    byId('limitations').hidden = !data.limitations?.length;
    byId('limitations').open = false;
    byId('limitations-list').replaceChildren(...(data.limitations || []).map((item) => element('li', item)));
    byId('source-count').textContent = data.sources.length + (data.sources.length === 1 ? ' source' : ' sources');
    byId('source-list').replaceChildren(...data.sources.map(renderSource));
    if (!data.sources.length) byId('source-list').append(element('p', 'No matching sources were found.', 'muted'));
    byId('report').hidden = false;
    byId('report-heading').focus();
}

function renderSource(source) {
    const card = element('article', '', 'card source');
    const attribution = [source.source_name || source.domain, formatDate(source.published_at)].filter(Boolean);
    card.append(
        badge(source.stance, stanceLabels[source.stance] || 'Provides context'),
        element('h3', source.title || 'Source article'),
        element('p', attribution.join(' · ')),
        element('p', source.evidence_snippet)
    );
    const url = publicWebUrl(source.url);
    if (url) {
        const link = element('a', 'Read source ↗');
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        card.append(link);
    }
    return card;
}

async function verify(event) {
    event.preventDefault();
    const button = byId('verify-button');
    if (button.disabled) return;
    const input = mode === 'text' ? textInput : urlInput;
    const value = input.value.trim();
    const invalid = mode === 'text' ? !value : !publicWebUrl(value);
    if (invalid) {
        message('verify-error', mode === 'text' ? 'Enter a claim to verify.' : 'Enter a valid HTTP or HTTPS article URL.');
        input.focus();
        return;
    }
    message('verify-error');
    button.disabled = true;
    byId('verify-label').textContent = 'Checking…';
    byId('progress').hidden = false;
    try {
        renderReport(await api('/verify', { method: 'POST', body: { [mode]: value } }));
    } catch (error) {
        message('verify-error', error.message);
    } finally {
        button.disabled = false;
        byId('verify-label').textContent = 'Verify claim';
        byId('progress').hidden = true;
    }
}

function openAccount(value) {
    accountMode = value;
    const profile = value === 'profile';
    const register = value === 'register';
    const heading = profile ? 'Your account' : register ? 'Create account' : 'Sign in';
    const form = byId('account-form');
    form.reset();
    message('account-error');
    byId('account-heading').textContent = heading;
    byId('name-field').hidden = !profile && !register;
    byId('name').required = profile || register;
    byId('name').value = profile ? user.full_name : '';
    byId('email').readOnly = profile;
    byId('email').value = profile ? user.email : '';
    byId('password').required = !profile;
    byId('password').minLength = register ? 6 : 0;
    byId('password').autocomplete = register ? 'new-password' : 'current-password';
    byId('password-label').textContent = profile ? 'Current password (for password changes)' : 'Password';
    byId('new-password-field').hidden = !profile;
    byId('account-submit').textContent = profile ? 'Save changes' : heading;
    byId('account-switch').textContent = profile ? 'Sign out' : register ? 'Sign in' : 'Create account';
    if (!accountDialog.open) accountDialog.showModal();
}

async function submitAccount(event) {
    event.preventDefault();
    const button = byId('account-submit');
    if (button.disabled) return;
    message('account-error');
    button.disabled = true;
    byId('account-switch').disabled = true;
    try {
        const password = byId('password').value;
        const fullName = byId('name').value.trim();
        if (accountMode === 'profile') {
            const body = { full_name: fullName };
            const newPassword = byId('new-password').value;
            if (newPassword) {
                if (!password) throw new Error('Enter your current password to set a new password.');
                Object.assign(body, { current_password: password, new_password: newPassword });
            }
            setSession(token, await api('/auth/me', { method: 'PUT', body }));
            notify('Account updated.');
        } else {
            const body = { email: byId('email').value.trim(), password };
            if (accountMode === 'register') body.full_name = fullName;
            const data = await api('/auth/' + accountMode, { method: 'POST', body, authenticated: false });
            setSession(data.access_token, data.user);
            notify('Signed in.');
        }
        accountDialog.close();
    } catch (error) {
        message('account-error', error.message);
    } finally {
        button.disabled = false;
        byId('account-switch').disabled = false;
    }
}

async function loadHistory(page) {
    const request = ++historyRequest;
    const list = byId('history-list');
    list.replaceChildren();
    byId('pagination').hidden = true;
    byId('clear-history').disabled = true;
    message('history-status', 'Loading history…');
    try {
        const params = { page };
        const verdictFilter = byId('history-filter').value;
        if (verdictFilter) params.verdict = verdictFilter;
        const query = new URLSearchParams(params);
        const data = await api('/history?' + query);
        if (request !== historyRequest || !historyDialog.open) return;
        if (page > Math.max(data.total_pages, 1)) {
            await loadHistory(Math.max(data.total_pages, 1));
            return;
        }
        historyPage = page;
        message('history-status', data.items.length ? '' : 'No saved reports match this view.');
        list.replaceChildren(...data.items.map(renderHistoryItem));
        byId('pagination').hidden = data.total_pages <= 1;
        byId('previous-page').disabled = page <= 1;
        byId('next-page').disabled = page >= data.total_pages;
        byId('history-page').textContent = 'Page ' + page + ' of ' + data.total_pages;
        byId('clear-history').disabled = data.total === 0 && !byId('history-filter').value;
    } catch (error) {
        if (request === historyRequest) message('history-status', error.message);
    }
}

function renderHistoryItem(item) {
    const row = document.createElement('li');
    const open = element('button', item.primary_claim, 'quiet history-item');
    open.append(element('small', [verdictLabels[item.verdict], formatDate(item.created_at)].filter(Boolean).join(' · ')));
    open.addEventListener('click', async () => {
        open.disabled = true;
        try {
            const saved = await api('/history/' + item.id);
            if (historyDialog.open) {
                historyDialog.close();
                renderReport(saved);
            }
        } catch (error) {
            message('history-status', error.message);
        } finally {
            open.disabled = false;
        }
    });
    const remove = element('button', 'Delete', 'quiet danger');
    remove.setAttribute('aria-label', 'Delete report for ' + item.primary_claim);
    remove.addEventListener('click', () => deleteHistory('/' + item.id, 'Delete this saved report?', remove));
    row.append(open, remove);
    return row;
}

async function deleteHistory(path, prompt, button) {
    if (!window.confirm(prompt)) return;
    button.disabled = true;
    try {
        await api('/history' + path, { method: 'DELETE' });
        if (historyDialog.open) await loadHistory(path ? historyPage : 1);
    } catch (error) {
        message('history-status', error.message);
        button.disabled = false;
    }
}

byId('mode-text').onclick = () => selectMode('text');
byId('mode-url').onclick = () => selectMode('url');
textInput.oninput = updateCount;
byId('verify-form').onsubmit = verify;
byId('clear').onclick = () => {
    const input = mode === 'text' ? textInput : urlInput;
    input.value = '';
    input.focus();
    updateCount();
    message('verify-error');
};
byId('paste').onclick = async () => {
    const input = mode === 'text' ? textInput : urlInput;
    try {
        const pasted = await navigator.clipboard.readText();
        if (pasted.length > input.maxLength) {
            message('verify-error', 'The pasted content exceeds the character limit.');
            return;
        }
        input.value = pasted;
        updateCount();
        message('verify-error');
    } catch {
        message('verify-error', 'Clipboard access is unavailable. Paste directly into the field.');
    } finally {
        input.focus();
    }
};
function reportText() {
    return [
        'VerifyNews — ' + verdictLabels[report.verdict] + ' (' + report.confidence + '% verification confidence)',
        report.claim.primary_claim, report.explanation || report.summary,
        ...(report.limitations || []),
        ...report.sources.map((source) => [source.title, publicWebUrl(source.url)].filter(Boolean).join(' — '))
    ].filter(Boolean).join('\n\n');
}

function openShareDialog(text) {
    byId('manual-copy').value = text;
    byId('share-device').hidden = typeof navigator.share !== 'function';
    message('share-status');
    if (!shareDialog.open) shareDialog.showModal();
}

async function copyReport(text) {
    try {
        await navigator.clipboard.writeText(text);
        if (shareDialog.open) {
            message('share-status', 'Report copied.');
        } else {
            notify('Report copied.');
        }
    } catch {
        openShareDialog(text);
        message('share-status', 'Clipboard access is unavailable. Copy the selected text manually.');
        const field = byId('manual-copy');
        field.focus();
        field.select();
    }
}

byId('copy-report').onclick = () => report && copyReport(reportText());
byId('share-report').onclick = () => report && openShareDialog(reportText());
byId('share-copy').onclick = () => copyReport(byId('manual-copy').value);
byId('share-device').onclick = async () => {
    try {
        await navigator.share({ title: 'VerifyNews report', text: byId('manual-copy').value });
    } catch (error) {
        if (error.name !== 'AbortError') message('share-status', 'Device sharing is unavailable. Use Copy text to share this report.');
    }
};
byId('print-report').onclick = () => window.print();
document.querySelectorAll('.example').forEach((button) => {
    button.onclick = () => {
        selectMode('text');
        textInput.value = button.querySelector('[data-claim]').textContent;
        updateCount();
        textInput.focus();
    };
});
byId('account-button').onclick = () => openAccount(user ? 'profile' : 'login');
byId('account-form').onsubmit = submitAccount;
byId('account-switch').onclick = () => {
    if (accountMode === 'profile') {
        setSession(null, null);
        accountDialog.close();
        notify('Signed out.');
    } else {
        openAccount(accountMode === 'login' ? 'register' : 'login');
    }
};
byId('history-button').onclick = () => {
    if (!user) {
        openAccount('login');
        message('account-error', 'Sign in to view your saved reports.');
        return;
    }
    historyDialog.showModal();
    loadHistory(1);
};
byId('history-filter').onchange = () => loadHistory(1);
byId('previous-page').onclick = () => loadHistory(historyPage - 1);
byId('next-page').onclick = () => loadHistory(historyPage + 1);
byId('clear-history').onclick = () => deleteHistory('', 'Delete all your saved reports?', byId('clear-history'));
document.querySelectorAll('[data-close]').forEach((button) => {
    button.onclick = () => byId(button.dataset.close).close();
});
accountDialog.addEventListener('cancel', (event) => {
    if (byId('account-submit').disabled) event.preventDefault();
});
accountDialog.addEventListener('close', () => byId('account-form').reset());
document.querySelector('[data-close="account-dialog"]').addEventListener('click', (event) => {
    if (byId('account-submit').disabled) event.stopImmediatePropagation();
}, true);
if (token) {
    const savedToken = token;
    api('/auth/me').then((profile) => {
        if (token === savedToken) setSession(savedToken, profile);
    }).catch(() => {});
}
