// Meme Coin Monitor Dashboard

// Detect base path from current URL (e.g., /apps/meme from /apps/meme/dashboard/)
const pathParts = window.location.pathname.split('/');
// Find 'dashboard' in path and get everything before it
const dashIdx = pathParts.indexOf('dashboard');
const BASE_PATH = dashIdx > 0 ? pathParts.slice(0, dashIdx).join('/') : '';
// Use same origin for API calls (auth cookies need same origin)
const API_BASE = window.location.origin + BASE_PATH;
let isConnected = false;
let refreshInterval = null;
let currentUsername = null;

// Settings with defaults
const DEFAULT_SETTINGS = {
    limitRisky: 100,
    limitOpportunities: 100,
    limitAlerts: 100
};

let settings = { ...DEFAULT_SETTINGS };

// Load settings from localStorage
function loadSettings() {
    try {
        const saved = localStorage.getItem('memeMonitorSettings');
        if (saved) {
            settings = { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
        }
    } catch (e) {
        console.error('Failed to load settings:', e);
    }
    return settings;
}

// Save settings to localStorage
function saveSettings() {
    try {
        localStorage.setItem('memeMonitorSettings', JSON.stringify(settings));
    } catch (e) {
        console.error('Failed to save settings:', e);
    }
}

// Update warning text based on limit value
function updateLimitWarning(selectId, warnId) {
    const select = document.getElementById(selectId);
    const warn = document.getElementById(warnId);
    if (!select || !warn) return;
    
    const value = parseInt(select.value);
    warn.className = 'setting-warning';
    
    if (value >= 5000) {
        warn.textContent = 'May be slow to load';
        warn.classList.add('warn-high');
    } else if (value >= 1000) {
        warn.textContent = 'Could take a few seconds';
        warn.classList.add('warn-medium');
    } else {
        warn.textContent = '';
    }
}

// Initialize settings UI
function initSettings() {
    loadSettings();
    
    // Set select values from settings
    const riskySelect = document.getElementById('limit-risky');
    const oppSelect = document.getElementById('limit-opportunities');
    const alertsSelect = document.getElementById('limit-alerts');
    
    if (riskySelect) riskySelect.value = settings.limitRisky;
    if (oppSelect) oppSelect.value = settings.limitOpportunities;
    if (alertsSelect) alertsSelect.value = settings.limitAlerts;
    
    // Add change listeners for warnings
    riskySelect?.addEventListener('change', () => updateLimitWarning('limit-risky', 'warn-risky'));
    oppSelect?.addEventListener('change', () => updateLimitWarning('limit-opportunities', 'warn-opportunities'));
    alertsSelect?.addEventListener('change', () => updateLimitWarning('limit-alerts', 'warn-alerts'));
    
    // Initial warning update
    updateLimitWarning('limit-risky', 'warn-risky');
    updateLimitWarning('limit-opportunities', 'warn-opportunities');
    updateLimitWarning('limit-alerts', 'warn-alerts');
    
    // Save button
    document.getElementById('save-settings')?.addEventListener('click', () => {
        settings.limitRisky = parseInt(riskySelect?.value || 100);
        settings.limitOpportunities = parseInt(oppSelect?.value || 100);
        settings.limitAlerts = parseInt(alertsSelect?.value || 100);
        saveSettings();
        
        const status = document.getElementById('settings-status');
        if (status) {
            status.innerHTML = '<div class="success-msg">Settings saved</div>';
            setTimeout(() => { status.innerHTML = ''; }, 3000);
        }
    });
    
    // Reset button
    document.getElementById('reset-settings')?.addEventListener('click', () => {
        settings = { ...DEFAULT_SETTINGS };
        saveSettings();
        
        if (riskySelect) riskySelect.value = DEFAULT_SETTINGS.limitRisky;
        if (oppSelect) oppSelect.value = DEFAULT_SETTINGS.limitOpportunities;
        if (alertsSelect) alertsSelect.value = DEFAULT_SETTINGS.limitAlerts;
        
        updateLimitWarning('limit-risky', 'warn-risky');
        updateLimitWarning('limit-opportunities', 'warn-opportunities');
        updateLimitWarning('limit-alerts', 'warn-alerts');
        
        const status = document.getElementById('settings-status');
        if (status) {
            status.innerHTML = '<div class="success-msg">Settings reset to defaults</div>';
            setTimeout(() => { status.innerHTML = ''; }, 3000);
        }
    });
}

// DOM Elements
const connectionStatus = document.getElementById('connection-status');
const lastUpdate = document.getElementById('last-update');
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication first
    const authenticated = await checkAuthentication();
    if (!authenticated) {
        window.location.href = BASE_PATH + '/login';
        return;
    }
    
    // Show API URL in footer
    document.getElementById('api-url').textContent = API_BASE;
    
    initTabs();
    initEventListeners();
    initLogout();
    initSettings();
    checkConnection();
    loadAllData();
    
    // Auto-refresh every 30 seconds
    refreshInterval = setInterval(() => {
        if (isConnected) {
            loadAllData();
        } else {
            checkConnection();
        }
    }, 30000);
});

// Authentication
async function checkAuthentication() {
    try {
        const response = await fetch(`${API_BASE}/auth/session`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.data?.authenticated) {
            currentUsername = data.data.username;
            const userSpan = document.getElementById('current-user');
            if (userSpan) {
                userSpan.textContent = currentUsername;
            }
            return true;
        }
    } catch (error) {
        console.error('Auth check failed:', error);
    }
    return false;
}

function initLogout() {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                await fetch(`${API_BASE}/auth/logout`, {
                    method: 'POST',
                    credentials: 'include'
                });
            } catch (error) {
                console.error('Logout error:', error);
            }
            window.location.href = BASE_PATH + '/login';
        });
    }
}

// Tab Navigation
function initTabs() {
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.dataset.tab;
            
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(tc => tc.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(targetId).classList.add('active');
        });
    });
}

// Current filter for recent alerts
let recentAlertsFilter = '';

// Event Listeners
function initEventListeners() {
    document.getElementById('refresh-risky')?.addEventListener('click', loadRiskyTokens);
    document.getElementById('refresh-opportunities')?.addEventListener('click', loadOpportunityTokens);
    document.getElementById('refresh-alerts')?.addEventListener('click', loadAllAlerts);
    document.getElementById('lookup-btn')?.addEventListener('click', lookupToken);
    document.getElementById('watch-add-btn')?.addEventListener('click', addToWatchlist);
    document.getElementById('watch-remove-btn')?.addEventListener('click', removeFromWatchlist);
    document.getElementById('alert-filter')?.addEventListener('change', loadAllAlerts);
    
    // Enter key for lookup
    document.getElementById('token-address')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') lookupToken();
    });
    
    // Alert filter pills
    initAlertPills();
}

function initAlertPills() {
    const pills = document.querySelectorAll('#alert-pills .pill');
    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            // Update active state
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            
            // Update filter and reload
            recentAlertsFilter = pill.dataset.filter || '';
            loadRecentAlerts();
        });
    });
}

// API Functions
async function apiCall(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    console.log('API call:', url);
    try {
        const response = await fetch(url, {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        console.log('Response status:', response.status);
        
        // Handle auth failures
        if (response.status === 401) {
            window.location.href = BASE_PATH + '/login';
            return null;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        console.log('Response data:', data);
        return data;
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}

async function checkConnection() {
    console.log('Checking connection to:', API_BASE);
    try {
        const result = await apiCall('/health');
        console.log('Health check result:', result);
        if (result.data?.status === 'ok') {
            setConnected(true);
            document.getElementById('api-status').textContent = 'ONLINE';
            document.getElementById('api-status').style.color = '#00ff00';
        }
    } catch (error) {
        console.error('Connection check failed:', error);
        setConnected(false);
        document.getElementById('api-status').textContent = 'OFFLINE';
        document.getElementById('api-status').style.color = '#ff4444';
    }
}

function setConnected(connected) {
    isConnected = connected;
    connectionStatus.textContent = connected ? 'CONNECTED' : 'DISCONNECTED';
    connectionStatus.className = `status ${connected ? 'connected' : 'disconnected'}`;
}

function updateLastUpdate() {
    const now = new Date();
    lastUpdate.textContent = `Last update: ${now.toLocaleTimeString()}`;
}

// Data Loading
async function loadAllData() {
    await Promise.all([
        loadOverviewStats(),
        loadRecentAlerts(),
        loadTopRisky(),
        loadTopOpportunities()
    ]);
    updateLastUpdate();
}

async function loadOverviewStats() {
    try {
        const [risky, opportunities, alerts] = await Promise.all([
            apiCall(`/tokens/risky?limit=${settings.limitRisky}`),
            apiCall(`/tokens/opportunities?limit=${settings.limitOpportunities}`),
            apiCall(`/alerts?limit=${settings.limitAlerts}`)
        ]);
        
        document.getElementById('risky-count').textContent = risky.data?.length || 0;
        document.getElementById('opportunity-count').textContent = opportunities.data?.length || 0;
        document.getElementById('alert-count').textContent = alerts.data?.length || 0;
    } catch (error) {
        document.getElementById('risky-count').textContent = '--';
        document.getElementById('opportunity-count').textContent = '--';
        document.getElementById('alert-count').textContent = '--';
    }
}

async function loadRecentAlerts() {
    const container = document.getElementById('recent-alerts');
    try {
        const url = recentAlertsFilter 
            ? `/alerts?type=${recentAlertsFilter}&limit=10`
            : '/alerts?limit=10';
        const result = await apiCall(url);
        const alerts = result.data || [];
        
        if (alerts.length === 0) {
            container.innerHTML = '<div class="loading">No alerts</div>';
            return;
        }
        
        container.innerHTML = alerts.map(alert => renderAlertItem(alert)).join('');
    } catch (error) {
        container.innerHTML = '<div class="error">Failed to load alerts</div>';
    }
}

async function loadTopRisky() {
    const container = document.getElementById('top-risky');
    try {
        const result = await apiCall('/tokens/risky?limit=5');
        const tokens = result.data || [];
        
        if (tokens.length === 0) {
            container.innerHTML = '<div class="loading">No risky tokens</div>';
            return;
        }
        
        container.innerHTML = tokens.map(token => renderTokenItem(token, 'risk')).join('');
    } catch (error) {
        container.innerHTML = '<div class="error">Failed to load</div>';
    }
}

async function loadTopOpportunities() {
    const container = document.getElementById('top-opportunities');
    try {
        const result = await apiCall('/tokens/opportunities?limit=5');
        const tokens = result.data || [];
        
        if (tokens.length === 0) {
            container.innerHTML = '<div class="loading">No opportunities</div>';
            return;
        }
        
        container.innerHTML = tokens.map(token => renderTokenItem(token, 'opportunity')).join('');
    } catch (error) {
        container.innerHTML = '<div class="error">Failed to load</div>';
    }
}

async function loadRiskyTokens() {
    const tbody = document.getElementById('risky-tbody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';
    
    try {
        const result = await apiCall(`/tokens/risky?limit=${settings.limitRisky}`);
        const tokens = result.data || [];
        
        if (tokens.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">No risky tokens found</td></tr>';
            return;
        }
        
        tbody.innerHTML = tokens.map(token => renderTokenRow(token)).join('');
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" class="error">Failed to load risky tokens</td></tr>';
    }
}

async function loadOpportunityTokens() {
    const tbody = document.getElementById('opportunities-tbody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Loading...</td></tr>';
    
    try {
        const result = await apiCall(`/tokens/opportunities?limit=${settings.limitOpportunities}`);
        const tokens = result.data || [];
        
        if (tokens.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">No opportunity tokens found</td></tr>';
            return;
        }
        
        tbody.innerHTML = tokens.map(token => renderTokenRow(token, true)).join('');
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" class="error">Failed to load opportunity tokens</td></tr>';
    }
}

async function loadAllAlerts() {
    const container = document.getElementById('all-alerts');
    const filterType = document.getElementById('alert-filter')?.value || '';
    
    container.innerHTML = '<div class="loading">Loading...</div>';
    
    try {
        const url = filterType 
            ? `/alerts?type=${filterType}&limit=${settings.limitAlerts}` 
            : `/alerts?limit=${settings.limitAlerts}`;
        const result = await apiCall(url);
        const alerts = result.data || [];
        
        if (alerts.length === 0) {
            container.innerHTML = '<div class="loading">No alerts found</div>';
            return;
        }
        
        container.innerHTML = alerts.map(alert => renderAlertItem(alert)).join('');
    } catch (error) {
        container.innerHTML = '<div class="error">Failed to load alerts</div>';
    }
}

async function lookupToken() {
    const address = document.getElementById('token-address').value.trim();
    const container = document.getElementById('token-result');
    
    if (!address) {
        container.innerHTML = '<div class="error">Please enter a token address</div>';
        return;
    }
    
    container.innerHTML = '<div class="loading">Analyzing...</div>';
    
    try {
        const result = await apiCall(`/token/${address}`);
        const token = result.data;
        
        if (!token) {
            container.innerHTML = '<div class="error">Token not found</div>';
            return;
        }
        
        container.innerHTML = renderTokenDetail(token);
    } catch (error) {
        container.innerHTML = `<div class="error">Failed to analyze token: ${error.message}</div>`;
    }
}

async function addToWatchlist() {
    const address = document.getElementById('watch-address').value.trim();
    const statusDiv = document.getElementById('watchlist-status');
    
    if (!address) {
        statusDiv.innerHTML = '<div class="error">Please enter a token address</div>';
        return;
    }
    
    try {
        await apiCall(`/watch/${address}`, { method: 'POST' });
        statusDiv.innerHTML = `<div class="success-msg">Added ${shortenAddress(address)} to watchlist</div>`;
        document.getElementById('watch-address').value = '';
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Failed to add to watchlist: ${error.message}</div>`;
    }
}

async function removeFromWatchlist() {
    const address = document.getElementById('watch-address').value.trim();
    const statusDiv = document.getElementById('watchlist-status');
    
    if (!address) {
        statusDiv.innerHTML = '<div class="error">Please enter a token address</div>';
        return;
    }
    
    try {
        await apiCall(`/watch/${address}`, { method: 'DELETE' });
        statusDiv.innerHTML = `<div class="success-msg">Removed ${shortenAddress(address)} from watchlist</div>`;
        document.getElementById('watch-address').value = '';
    } catch (error) {
        statusDiv.innerHTML = `<div class="error">Failed to remove from watchlist: ${error.message}</div>`;
    }
}

// Render Functions
function renderAlertItem(alert) {
    const severity = alert.severity?.toLowerCase() || 'medium';
    const time = formatTime(alert.created_at);
    
    return `
        <div class="alert-item">
            <div class="alert-header">
                <span class="alert-type ${severity}">${alert.alert_type?.toUpperCase() || 'ALERT'}</span>
                <span class="alert-time">${time}</span>
            </div>
            <div class="alert-message">${alert.message || 'No message'}</div>
            <div class="alert-token" onclick="copyAddress('${alert.token_address}')">${shortenAddress(alert.token_address)}</div>
        </div>
    `;
}

function renderTokenItem(token, scoreType) {
    const score = scoreType === 'risk' ? token.risk_score : token.opportunity_score;
    const scoreClass = getScoreClass(score, scoreType === 'risk');
    
    return `
        <div class="token-item">
            <span class="token-address" onclick="copyAddress('${token.address}')">${shortenAddress(token.address)}</span>
            <span class="score ${scoreClass}">${score ?? '--'}</span>
        </div>
    `;
}

function renderTokenRow(token, opportunityFirst = false) {
    const riskClass = getScoreClass(token.risk_score, true);
    const oppClass = getScoreClass(token.opportunity_score, false);
    const time = formatTime(token.timestamp);
    
    if (opportunityFirst) {
        return `
            <tr>
                <td><span class="address" onclick="copyAddress('${token.address}')">${shortenAddress(token.address)}</span></td>
                <td><span class="score ${oppClass}">${token.opportunity_score ?? '--'}</span></td>
                <td><span class="score ${riskClass}">${token.risk_score ?? '--'}</span></td>
                <td>${token.confidence || '--'}</td>
                <td>${time}</td>
            </tr>
        `;
    }
    
    return `
        <tr>
            <td><span class="address" onclick="copyAddress('${token.address}')">${shortenAddress(token.address)}</span></td>
            <td><span class="score ${riskClass}">${token.risk_score ?? '--'}</span></td>
            <td><span class="score ${oppClass}">${token.opportunity_score ?? '--'}</span></td>
            <td>${token.confidence || '--'}</td>
            <td>${time}</td>
        </tr>
    `;
}

function renderTokenDetail(token) {
    const riskClass = getScoreClass(token.risk_score, true);
    const oppClass = getScoreClass(token.opportunity_score, false);
    
    return `
        <div class="token-detail-grid">
            <div class="detail-item">
                <div class="detail-label">ADDRESS</div>
                <div class="detail-value" style="font-size: 11px; cursor: pointer;" onclick="copyAddress('${token.address}')">${token.address}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">RISK SCORE</div>
                <div class="detail-value"><span class="score ${riskClass}">${token.risk_score ?? '--'}</span></div>
            </div>
            <div class="detail-item">
                <div class="detail-label">OPPORTUNITY SCORE</div>
                <div class="detail-value"><span class="score ${oppClass}">${token.opportunity_score ?? '--'}</span></div>
            </div>
            <div class="detail-item">
                <div class="detail-label">PRICE (USD)</div>
                <div class="detail-value">${token.price_usd ? '$' + parseFloat(token.price_usd).toFixed(8) : '--'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">MARKET CAP</div>
                <div class="detail-value">${token.market_cap ? formatNumber(token.market_cap) : '--'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">LIQUIDITY</div>
                <div class="detail-value">${token.liquidity_usd ? '$' + formatNumber(token.liquidity_usd) : '--'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">HOLDERS</div>
                <div class="detail-value">${token.holder_count ?? '--'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">TOP 10 HOLDERS</div>
                <div class="detail-value">${token.top_10_pct ? token.top_10_pct.toFixed(1) + '%' : '--'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">CONFIDENCE</div>
                <div class="detail-value">${token.confidence || '--'}</div>
            </div>
        </div>
    `;
}

// Utility Functions
function shortenAddress(address) {
    if (!address) return '--';
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function copyAddress(address) {
    navigator.clipboard.writeText(address).then(() => {
        // Could show a toast here
        console.log('Copied:', address);
    });
}

function formatTime(timestamp) {
    if (!timestamp) return '--';
    const date = new Date(timestamp);
    return date.toLocaleString();
}

function formatNumber(num) {
    if (!num) return '--';
    const n = parseFloat(num);
    if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(2) + 'K';
    return n.toFixed(2);
}

function getScoreClass(score, isRisk = true) {
    if (score === null || score === undefined) return '';
    
    if (isRisk) {
        if (score >= 75) return 'critical';
        if (score >= 50) return 'high';
        if (score >= 25) return 'medium';
        return 'low';
    } else {
        if (score >= 75) return 'low'; // high opportunity = green
        if (score >= 50) return 'medium';
        if (score >= 25) return 'high';
        return 'critical';
    }
}

// Load data when switching tabs
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        const targetId = tab.dataset.tab;
        
        if (targetId === 'risky') loadRiskyTokens();
        if (targetId === 'opportunities') loadOpportunityTokens();
        if (targetId === 'alerts') loadAllAlerts();
    });
});
