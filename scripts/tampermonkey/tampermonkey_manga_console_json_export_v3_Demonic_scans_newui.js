// ==UserScript==
// @name         Demonic Scans Image Link Exporter — New UI
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  Collecte les liens d'images de manhwa/manga par chapitre, télécharge directement le JSON. Interface glassmorphism.
// @author       Assistant
// @match        http://*/*
// @match        https://*/*
// @include      *
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @grant        GM_info
// @run-at       document-end
// @noframes
// ==/UserScript==

(function() {
    'use strict';

    if (window.manhwaImageLinkConsoleExporterLoaded) {
        return;
    }
    window.manhwaImageLinkConsoleExporterLoaded = true;

    const CONFIG = {
        projectTitleSelector: 'h1.big-fat-titles',
        chapterListSelector: 'a.chplinks',
        imageSelector: 'img.imgholder',
        nextImageSelector: null,

        delayBetweenChapters: 1000,
        delayBetweenPages: 500,
        pageLoadDelay: 2000,

        enabledDomains: [
            'manhwa',
            'manga',
            'webtoon',
            'scan',
            'read'
        ]
    };

    if (!shouldActivate()) {
        return;
    }

    let isCollecting = false;
    let currentProject = '';
    let chapterQueue = [];
    let collectedData = {}; // Sera un objet qui contiendra 'projectName' et 'chapters'
    let currentChapterIndex = 0;
    let totalChapters = 0;

    function shouldActivate() {
        const hostname = window.location.hostname.toLowerCase();
        return CONFIG.enabledDomains.some(domain => hostname.includes(domain));
    }

    function sanitizeFilename(filename) {
        return filename.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    }

    function getProjectName() {
        const titleElement = document.querySelector(CONFIG.projectTitleSelector);
        if (titleElement) {
            return sanitizeFilename(titleElement.textContent.trim());
        }
        return sanitizeFilename(document.title.replace(/chapter|ch|read|online|manga|manhwa|webtoon/gi, '').trim()) || 'manhwa_project';
    }

    function extractChapterNumber(url, text = '') {
        if (!url && !text) return '000';

        const urlMatch = url ? (url.match(/chapter[_-]?(\d+(?:\.\d+)?)/i) ||
                               url.match(/ch[_-]?(\d+(?:\.\d+)?)/i) ||
                               url.match(/\/(\d+(?:\.\d+)?)(?:\/|$)/)) : null;
        if (urlMatch) {
            const number = Array.isArray(urlMatch) ? urlMatch[1] || urlMatch[urlMatch.length - 1] : urlMatch[1];
            if (number) return number.replace(/\.$/, '');
        }

        if (text) {
            const textMatch = text.match(/chapter\s*(\d+(?:\.\d+)?)/i) ||
                             text.match(/ch\s*(\d+(?:\.\d+)?)/i) ||
                             text.match(/(\d+(?:\.\d+)?)/);
            if (textMatch) {
                return textMatch[1].replace(/\.$/, '');
            }
        }

        return (url ? String(url.hashCode() % 100000) : Date.now().toString()).slice(-6);
    }

    if (!String.prototype.hashCode) {
        String.prototype.hashCode = function() {
            let hash = 0, i, chr;
            if (this.length === 0) return hash;
            for (i = 0; i < this.length; i++) {
                chr = this.charCodeAt(i);
                hash = ((hash << 5) - hash) + chr;
                hash |= 0;
            }
            return Math.abs(hash);
        };
    }

    async function loadPageContent(url, retries = 3) {
        if (!url || url === 'undefined') {
            throw new Error('URL invalide ou undefined');
        }

        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                updateStatus(`Chargement (tentative ${attempt}/${retries}): ${url.split('?')[0]}`);
                
                const response = await fetch(url, {
                    headers: {
                        'Referer': window.location.href,
                        'User-Agent': navigator.userAgent,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
                        'Cache-Control': 'no-cache'
                    },
                    mode: 'cors',
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    if (response.status === 429 || response.status === 503) {
                        const retryAfter = response.headers.get('Retry-After');
                        const waitTime = retryAfter ? parseInt(retryAfter, 10) * 1000 : Math.min(5000 * attempt, 30000);
                        await new Promise(resolve => setTimeout(resolve, waitTime));
                        continue;
                    }
                    throw new Error(`HTTP ${response.status} - ${response.statusText}`);
                }

                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');

                if (!doc || !doc.body) {
                    throw new Error('Document HTML invalide ou vide');
                }

                return doc;

            } catch (error) {
                updateStatus(`Erreur chargement page: ${error.message}`);
                if (attempt === retries) {
                    throw error;
                }
                const waitTime = Math.min(2000 * attempt, 10000);
                await new Promise(resolve => setTimeout(resolve, waitTime));
            }
        }
    }

    function extractImagesFromDocument(doc, chapterNumber, customSelector = null) {
        const imageUrls = [];
        const selectorsToTry = [
            customSelector,
            CONFIG.imageSelector,
            'img[src]',
            'img[data-src]',
            'img[data-original]',
            'img[data-lazy]',
            'img.lazy',
            'img.lazyload',
            'img[srcset]',
            'img'
        ].filter(s => s);

        const uniqueUrls = new Set();

        for (const selector of selectorsToTry) {
            if (!selector) continue;
            const images = doc.querySelectorAll(selector);
            images.forEach((img) => {
                let imageUrl = img.src || img.dataset.src || img.dataset.original ||
                               img.getAttribute('data-src') || img.getAttribute('data-original') ||
                               img.getAttribute('data-lazy');

                if (!imageUrl && img.hasAttribute('srcset')) {
                    const srcset = img.getAttribute('srcset');
                    if (srcset) {
                        const firstSrc = srcset.split(',')[0].trim().split(' ')[0];
                        if (firstSrc) imageUrl = firstSrc;
                    }
                }

                if (imageUrl) {
                    if (imageUrl.startsWith('//')) {
                        imageUrl = window.location.protocol + imageUrl;
                    } else if (imageUrl.startsWith('/')) {
                        try {
                            imageUrl = new URL(imageUrl, doc.baseURI || window.location.href).href;
                        } catch (e) {
                            return;
                        }
                    } else if (!imageUrl.startsWith('http')) {
                         try {
                            imageUrl = new URL(imageUrl, doc.baseURI || window.location.href).href;
                        } catch (e) {
                            return;
                        }
                    }

                    if (imageUrl &&
                        !imageUrl.includes('data:image') &&
                        !imageUrl.includes('placeholder') &&
                        !imageUrl.includes('loading') &&
                        !imageUrl.includes('blank.gif') &&
                        !imageUrl.includes('empty.png') &&
                        imageUrl.length > 10 &&
                        !uniqueUrls.has(imageUrl)) {
                        
                        imageUrls.push(imageUrl);
                        uniqueUrls.add(imageUrl);
                    }
                }
            });
            if (imageUrls.length > 0) {
                break;
            }
        }
        return imageUrls;
    }

    async function collectChapterImages(chapterUrl, chapterNumber, chapterText) {
        if (!chapterUrl || chapterUrl === 'undefined') {
            return;
        }

        if (!chapterNumber || chapterNumber === 'undefined') {
            chapterNumber = extractChapterNumber(chapterUrl, chapterText);
        }

        const chapterKey = `Chapitre ${chapterNumber}${chapterText ? ` - ${chapterText}` : ''}`;
        
        // Assurez-vous que 'chapters' existe et que l'entrée pour ce chapitre est initialisée
        if (!collectedData.chapters) {
            collectedData.chapters = {};
        }
        if (!collectedData.chapters[chapterKey]) {
            collectedData.chapters[chapterKey] = {
                url: chapterUrl,
                images: []
            };
        }

        let currentPageUrl = chapterUrl;
        let pageIndex = 1;

        while (currentPageUrl && isCollecting) {
            try {
                updateStatus(`Chapitre ${chapterNumber}, page ${pageIndex}: chargement...`);

                const doc = await loadPageContent(currentPageUrl);
                let imageUrls = extractImagesFromDocument(doc, chapterNumber);

                if (imageUrls.length > 0) {
                    collectedData.chapters[chapterKey].images.push(...imageUrls);
                    updateStatus(`Chapitre ${chapterNumber}: ${collectedData.chapters[chapterKey].images.length} images collectées.`);
                }

                if (CONFIG.nextImageSelector) {
                    const nextImageLinkElement = doc.querySelector(CONFIG.nextImageSelector);
                    if (nextImageLinkElement && nextImageLinkElement.href &&
                        new URL(nextImageLinkElement.href).pathname !== new URL(currentPageUrl).pathname) {
                        currentPageUrl = nextImageLinkElement.href;
                        pageIndex++;
                        await new Promise(resolve => setTimeout(resolve, CONFIG.delayBetweenPages));
                    } else {
                        currentPageUrl = null;
                    }
                } else {
                    currentPageUrl = null;
                }

            } catch (error) {
                updateStatus(`Erreur chapitre ${chapterNumber} page ${pageIndex}: ${error.message}`);
                currentPageUrl = null;
            }
        }
    }

    async function processChapterQueue() {
        // Initialiser le nom du projet au début de la collecte principale
        collectedData.projectName = getProjectName();
        collectedData.chapters = {}; // S'assurer que les chapitres sont initialisés

        while (chapterQueue.length > 0 && isCollecting) {
            const chapterData = chapterQueue.shift();
            currentChapterIndex = totalChapters - chapterQueue.length;

            await collectChapterImages(chapterData.url, chapterData.number, chapterData.text);

            if (chapterQueue.length > 0) {
                await new Promise(resolve => setTimeout(resolve, CONFIG.delayBetweenChapters));
            }
        }

        if (isCollecting) {
            updateStatus('Collecte terminée. Téléchargement du JSON...');
            isCollecting = false;
            displayCollectedDataInConsole();
            downloadCollectedDataAsJson();
            clearState();
        }
    }

    function collectChapterLinks() {
        const chapterLinks = document.querySelectorAll(CONFIG.chapterListSelector);
        const chapters = [];

        chapterLinks.forEach(link => {
            const url = link.href;
            const text = link.textContent.trim();
            const chapterNumber = extractChapterNumber(url, text);

            if (url && url !== window.location.href && !url.startsWith('javascript:')) {
                chapters.push({
                    url: url,
                    number: chapterNumber,
                    text: text
                });
            }
        });

        chapters.sort((a, b) => {
            const numA = parseFloat(a.number) || 0;
            const numB = parseFloat(b.number) || 0;
            if (numA !== numB) {
                return numA - numB;
            }
            return a.text.localeCompare(b.text);
        });

        return chapters;
    }

    function displayCollectedDataInConsole() {
        console.groupCollapsed(`📚 Liens d'images pour le projet: ${collectedData.projectName || 'Inconnu'}`);
        console.log(JSON.stringify(collectedData, null, 2));
        console.groupEnd();
        console.log(`✅ Les liens d'images pour "${collectedData.projectName || 'le projet'}" ont été affichés dans la console.`);
    }

    function downloadCollectedDataAsJson() {
        const projectName = collectedData.projectName || 'manhwa_project';
        const json = JSON.stringify(collectedData, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const link = document.createElement('a');
        link.href = url;
        link.download = `${projectName}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        URL.revokeObjectURL(url);
        updateStatus(`💾 Fichier "${projectName}.json" téléchargé.`);
    }

    function injectStyles() {
        if (document.getElementById('mle-glass-styles')) return;
        const style = document.createElement('style');
        style.id = 'mle-glass-styles';
        style.textContent = `
            @keyframes mle-fade-in {
                from { opacity: 0; transform: translateY(-12px) scale(.97); }
                to   { opacity: 1; transform: translateY(0) scale(1); }
            }
            @keyframes mle-shimmer {
                0%   { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }
            @keyframes mle-pulse {
                0%, 100% { opacity: 1; }
                50%      { opacity: .45; }
            }
            @keyframes mle-spin {
                to { transform: rotate(360deg); }
            }

            #manhwa-link-exporter-ui, #manhwa-link-exporter-ui * {
                box-sizing: border-box;
            }

            #manhwa-link-exporter-ui {
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 2147483647;
                width: 330px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                             'Helvetica Neue', Arial, sans-serif;
                font-size: 13px;
                line-height: 1.5;
                color: #f4f6fb;
                animation: mle-fade-in .45s cubic-bezier(.22,1,.36,1);
            }

            #manhwa-link-exporter-ui.mle-collapsed .mle-body {
                display: none;
            }

            .mle-card {
                position: relative;
                padding: 18px;
                border-radius: 20px;
                background: linear-gradient(145deg,
                            rgba(255,255,255,.16),
                            rgba(255,255,255,.06));
                backdrop-filter: blur(22px) saturate(180%);
                -webkit-backdrop-filter: blur(22px) saturate(180%);
                border: 1px solid rgba(255,255,255,.22);
                box-shadow: 0 8px 32px rgba(0,0,0,.38),
                            inset 0 1px 0 rgba(255,255,255,.28);
                overflow: hidden;
            }

            /* Halo coloré derrière le verre */
            .mle-card::before {
                content: '';
                position: absolute;
                inset: -60% -20% auto -20%;
                height: 190px;
                background: radial-gradient(circle at 25% 40%, rgba(129,140,248,.55), transparent 62%),
                            radial-gradient(circle at 75% 30%, rgba(236,72,153,.42), transparent 60%);
                filter: blur(26px);
                pointer-events: none;
                z-index: 0;
            }

            .mle-card > * { position: relative; z-index: 1; }

            .mle-header {
                display: flex;
                align-items: center;
                gap: 9px;
                margin-bottom: 4px;
            }

            .mle-logo {
                width: 26px;
                height: 26px;
                flex: 0 0 26px;
                display: grid;
                place-items: center;
                border-radius: 9px;
                font-size: 14px;
                background: linear-gradient(135deg, rgba(129,140,248,.95), rgba(236,72,153,.9));
                box-shadow: 0 3px 10px rgba(99,102,241,.5);
            }

            .mle-title {
                margin: 0;
                font-size: 14px;
                font-weight: 650;
                letter-spacing: .2px;
                text-shadow: 0 1px 3px rgba(0,0,0,.35);
                flex: 1;
            }

            .mle-collapse {
                width: 24px;
                height: 24px;
                flex: 0 0 24px;
                border: 1px solid rgba(255,255,255,.24);
                border-radius: 8px;
                background: rgba(255,255,255,.10);
                color: #f4f6fb;
                cursor: pointer;
                font-size: 13px;
                line-height: 1;
                display: grid;
                place-items: center;
                transition: background .2s ease, transform .2s ease;
            }
            .mle-collapse:hover {
                background: rgba(255,255,255,.2);
                transform: scale(1.08);
            }

            .mle-host {
                font-size: 10.5px;
                letter-spacing: .3px;
                text-transform: uppercase;
                color: rgba(244,246,251,.62);
                margin-bottom: 12px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .mle-status-box {
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 9px 11px;
                margin-bottom: 11px;
                border-radius: 12px;
                background: rgba(255,255,255,.09);
                border: 1px solid rgba(255,255,255,.14);
                min-height: 38px;
            }

            .mle-dot {
                width: 7px;
                height: 7px;
                flex: 0 0 7px;
                border-radius: 50%;
                background: #34d399;
                box-shadow: 0 0 8px rgba(52,211,153,.85);
            }
            #manhwa-link-exporter-ui.mle-busy .mle-dot {
                background: #fbbf24;
                box-shadow: 0 0 8px rgba(251,191,36,.85);
                animation: mle-pulse 1.15s ease-in-out infinite;
            }

            .mle-status-text {
                font-size: 12px;
                color: rgba(244,246,251,.94);
                word-break: break-word;
                flex: 1;
            }

            .mle-progress-wrap { display: none; margin-bottom: 12px; }
            #manhwa-link-exporter-ui.mle-busy .mle-progress-wrap { display: block; }

            .mle-progress-meta {
                display: flex;
                justify-content: space-between;
                font-size: 10.5px;
                color: rgba(244,246,251,.68);
                margin-bottom: 5px;
                font-variant-numeric: tabular-nums;
            }

            .mle-progress-track {
                height: 7px;
                border-radius: 99px;
                background: rgba(0,0,0,.28);
                overflow: hidden;
                border: 1px solid rgba(255,255,255,.10);
            }

            .mle-progress-fill {
                height: 100%;
                width: 0%;
                border-radius: 99px;
                background: linear-gradient(90deg, #818cf8, #22d3ee, #ec4899, #818cf8);
                background-size: 200% 100%;
                animation: mle-shimmer 2.1s linear infinite;
                transition: width .35s cubic-bezier(.22,1,.36,1);
            }

            .mle-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
                margin-bottom: 8px;
            }

            .mle-btn {
                position: relative;
                padding: 9px 10px;
                border-radius: 12px;
                border: 1px solid rgba(255,255,255,.20);
                background: rgba(255,255,255,.10);
                color: #f4f6fb;
                font-family: inherit;
                font-size: 12px;
                font-weight: 560;
                cursor: pointer;
                transition: transform .16s ease, background .2s ease,
                            box-shadow .2s ease, border-color .2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                white-space: nowrap;
            }
            .mle-btn:hover:not(:disabled) {
                background: rgba(255,255,255,.19);
                transform: translateY(-1.5px);
                box-shadow: 0 6px 16px rgba(0,0,0,.28);
            }
            .mle-btn:active:not(:disabled) { transform: translateY(0); }
            .mle-btn:disabled { opacity: .4; cursor: not-allowed; }
            .mle-btn:focus-visible {
                outline: 2px solid rgba(129,140,248,.9);
                outline-offset: 2px;
            }

            .mle-btn-start {
                background: linear-gradient(135deg, rgba(52,211,153,.9), rgba(16,185,129,.82));
                border-color: rgba(52,211,153,.5);
                box-shadow: 0 4px 14px rgba(16,185,129,.34);
            }
            .mle-btn-start:hover:not(:disabled) {
                background: linear-gradient(135deg, rgba(52,211,153,1), rgba(16,185,129,.95));
            }

            .mle-btn-stop {
                background: linear-gradient(135deg, rgba(248,113,113,.88), rgba(239,68,68,.8));
                border-color: rgba(248,113,113,.5);
                box-shadow: 0 4px 14px rgba(239,68,68,.32);
            }
            .mle-btn-stop:hover:not(:disabled) {
                background: linear-gradient(135deg, rgba(248,113,113,1), rgba(239,68,68,.95));
            }

            .mle-btn-download {
                width: 100%;
                background: linear-gradient(135deg, rgba(129,140,248,.92), rgba(168,85,247,.85));
                border-color: rgba(129,140,248,.55);
                box-shadow: 0 4px 16px rgba(129,140,248,.38);
                font-weight: 620;
                padding: 11px 10px;
            }
            .mle-btn-download:hover:not(:disabled) {
                background: linear-gradient(135deg, rgba(129,140,248,1), rgba(168,85,247,.96));
            }

            .mle-divider {
                height: 1px;
                margin: 12px 0 11px;
                background: linear-gradient(90deg, transparent,
                            rgba(255,255,255,.24), transparent);
            }

            .mle-stats {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
                margin-bottom: 11px;
            }

            .mle-stat {
                padding: 8px 10px;
                border-radius: 11px;
                background: rgba(0,0,0,.20);
                border: 1px solid rgba(255,255,255,.10);
            }

            .mle-stat-label {
                font-size: 9.5px;
                letter-spacing: .5px;
                text-transform: uppercase;
                color: rgba(244,246,251,.55);
                margin-bottom: 2px;
            }

            .mle-stat-value {
                font-size: 15px;
                font-weight: 680;
                font-variant-numeric: tabular-nums;
                color: #fff;
            }

            .mle-project {
                display: flex;
                align-items: baseline;
                gap: 6px;
                font-size: 11px;
                color: rgba(244,246,251,.62);
            }
            .mle-project-name {
                color: #fff;
                font-weight: 600;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            @media (prefers-reduced-motion: reduce) {
                #manhwa-link-exporter-ui,
                .mle-progress-fill,
                .mle-dot { animation: none !important; }
                .mle-btn { transition: none; }
            }
        `;
        document.head.appendChild(style);
    }

    function createUI() {
        injectStyles();

        const ui = document.createElement('div');
        ui.id = 'manhwa-link-exporter-ui';
        ui.innerHTML = `
            <div class="mle-card">
                <div class="mle-header">
                    <div class="mle-logo">🔗</div>
                    <h3 class="mle-title">Manhwa Exporter</h3>
                    <button class="mle-collapse" id="mle-toggle" title="Réduire / agrandir">−</button>
                </div>
                <div class="mle-body">
                    <div class="mle-host">${window.location.hostname}</div>

                    <div class="mle-status-box">
                        <span class="mle-dot"></span>
                        <span class="mle-status-text" id="status">Prêt à collecter</span>
                    </div>

                    <div class="mle-progress-wrap" id="progress-bar">
                        <div class="mle-progress-meta">
                            <span id="mle-progress-label">Progression</span>
                            <span id="mle-progress-pct">0%</span>
                        </div>
                        <div class="mle-progress-track">
                            <div class="mle-progress-fill" id="progress-fill"></div>
                        </div>
                    </div>

                    <div class="mle-stats">
                        <div class="mle-stat">
                            <div class="mle-stat-label">Chapitres</div>
                            <div class="mle-stat-value" id="mle-stat-chapters">0</div>
                        </div>
                        <div class="mle-stat">
                            <div class="mle-stat-label">Images</div>
                            <div class="mle-stat-value" id="mle-stat-images">0</div>
                        </div>
                    </div>

                    <div class="mle-grid">
                        <button class="mle-btn mle-btn-start" id="start-collection">▶ Démarrer</button>
                        <button class="mle-btn mle-btn-stop" id="stop-collection">■ Arrêter</button>
                    </div>
                    <div class="mle-grid">
                        <button class="mle-btn" id="test-selectors">🎯 Sélecteurs</button>
                        <button class="mle-btn" id="collect-current">📄 Page actuelle</button>
                    </div>

                    <div class="mle-divider"></div>

                    <button class="mle-btn mle-btn-download" id="download-json">💾 Télécharger le JSON</button>

                    <div class="mle-divider"></div>

                    <div class="mle-project">
                        <span>Projet :</span>
                        <span class="mle-project-name" id="project-name">${getProjectName()}</span>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(ui);

        document.getElementById('start-collection').addEventListener('click', startCollection);
        document.getElementById('stop-collection').addEventListener('click', stopCollection);
        document.getElementById('test-selectors').addEventListener('click', testSelectors);
        document.getElementById('collect-current').addEventListener('click', collectCurrentPage);
        document.getElementById('download-json').addEventListener('click', () => {
            if (!collectedData.chapters || Object.keys(collectedData.chapters).length === 0) {
                updateStatus('⚠️ Aucune donnée collectée à télécharger.');
                return;
            }
            downloadCollectedDataAsJson();
        });

        const toggle = document.getElementById('mle-toggle');
        toggle.addEventListener('click', () => {
            const collapsed = ui.classList.toggle('mle-collapsed');
            toggle.textContent = collapsed ? '+' : '−';
        });
    }

    function updateStats() {
        const chapters = (collectedData && collectedData.chapters) ? collectedData.chapters : {};
        const chapterCount = Object.keys(chapters).length;
        const imageCount = Object.values(chapters)
            .reduce((sum, ch) => sum + ((ch && ch.images) ? ch.images.length : 0), 0);

        const chapterEl = document.getElementById('mle-stat-chapters');
        const imageEl = document.getElementById('mle-stat-images');
        const projectEl = document.getElementById('project-name');

        if (chapterEl) chapterEl.textContent = chapterCount;
        if (imageEl) imageEl.textContent = imageCount;
        if (projectEl && collectedData && collectedData.projectName) {
            projectEl.textContent = collectedData.projectName;
        }

        const ui = document.getElementById('manhwa-link-exporter-ui');
        if (ui) ui.classList.toggle('mle-busy', isCollecting);
    }

    function updateProgress() {
        const progressFill = document.getElementById('progress-fill');
        const progressPct = document.getElementById('mle-progress-pct');
        const progressLabel = document.getElementById('mle-progress-label');

        if (progressFill && totalChapters > 0) {
            const done = totalChapters - chapterQueue.length;
            const percentage = (done / totalChapters * 100).toFixed(1);
            progressFill.style.width = percentage + '%';
            if (progressPct) progressPct.textContent = percentage + '%';
            if (progressLabel) progressLabel.textContent = `Chapitre ${done} / ${totalChapters}`;
        }

        updateStats();
    }

    async function collectCurrentPage() {
        if (isCollecting) {
            updateStatus('Une collecte est déjà en cours.');
            return;
        }

        isCollecting = true;
        collectedData = {
            projectName: getProjectName(),
            chapters: {}
        };
        chapterQueue = [];
        currentChapterIndex = 0;
        totalChapters = 1;

        updateStatus(`Collecte de liens pour la page actuelle...`);

        try {
            const chapterNumber = extractChapterNumber(window.location.href, document.title);
            await collectChapterImages(window.location.href, chapterNumber, document.title);
            
            updateStatus(`Collecte de la page actuelle terminée! ${Object.values(collectedData.chapters).flat().length} liens collectés.`);
            displayCollectedDataInConsole();
            downloadCollectedDataAsJson();
        } catch (error) {
            updateStatus(`Erreur page actuelle: ${error.message}`);
        } finally {
            isCollecting = false;
            updateProgress();
        }
    }

    function testSelectors() {
        updateStatus('Test des sélecteurs...');

        const title = document.querySelector(CONFIG.projectTitleSelector);
        console.log('Titre (projectTitleSelector):', title ? title.textContent.trim() : 'AUCUN (Vérifiez CONFIG.projectTitleSelector)');

        const chapters = document.querySelectorAll(CONFIG.chapterListSelector);
        console.log('Chapitres (chapterListSelector):', chapters.length, chapters.length > 0 ? '(OK)' : '(Vérifiez CONFIG.chapterListSelector)');
        chapters.forEach((ch, i) => {
            if (i < 5) console.log(`  - Ex. Chapitre ${i+1}: "${ch.textContent.trim()}" (URL: ${ch.href})`);
        });
        if (chapters.length > 5) console.log(`  ... et ${chapters.length - 5} autres.`);

        const images = document.querySelectorAll(CONFIG.imageSelector);
        console.log('Images (imageSelector):', images.length, images.length > 0 ? '(OK)' : '(Vérifiez CONFIG.imageSelector)');
        images.forEach((img, i) => {
            if (i < 5) console.log(`  - Ex. Image ${i+1}: src="${img.src || img.dataset.src || 'pas de src'}"`);
        });
        if (images.length > 5) console.log(`  ... et ${images.length - 5} autres.`);

        if (CONFIG.nextImageSelector) {
            const nextImage = document.querySelector(CONFIG.nextImageSelector);
            console.log('Bouton/Lien "Image/Page Suivante" (nextImageSelector):', nextImage ? 'TROUVÉ (URL: ' + nextImage.href + ')' : 'AUCUN (Vérifiez CONFIG.nextImageSelector si chapitre multi-pages)');
        } else {
            console.log('Sélecteur "nextImageSelector" n\'est pas configuré. Si les chapitres ont plusieurs pages, configurez-le.');
        }

        updateStatus(`Test terminé: ${chapters.length} chapitres, ${images.length} images détectées sur cette page.`);
    }

    function updateStatus(message) {
        const statusElement = document.getElementById('status');
        if (statusElement) {
            statusElement.textContent = message;
        }
        updateProgress();
    }

    async function startCollection() {
        if (isCollecting) {
            updateStatus('Une collecte est déjà en cours.');
            return;
        }

        isCollecting = true;
        // Initialise l'objet collectedData ici avec le nom du projet
        collectedData = {
            projectName: getProjectName(),
            chapters: {}
        };
        currentChapterIndex = 0;

        updateStatus('Collecte des chapitres...');

        try {
            chapterQueue = collectChapterLinks();
            totalChapters = chapterQueue.length;

            if (totalChapters > 0) {
                updateStatus(`Début de la collecte de ${totalChapters} chapitres...`);
                await processChapterQueue();
            } else {
                updateStatus('Aucun chapitre trouvé pour la collecte.');
                isCollecting = false;
            }

        } catch (error) {
            updateStatus(`Erreur générale: ${error.message}`);
            isCollecting = false;
        } finally {
            updateProgress();
        }
    }

    function stopCollection() {
        isCollecting = false;
        chapterQueue = [];
        totalChapters = 0;
        currentChapterIndex = 0;
        clearState();
        updateStatus('Collecte arrêtée');
    }

    function init() {
        try {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', init);
                return;
            }

            if (document.getElementById('manhwa-link-exporter-ui')) {
                return;
            }

            createUI();
            restoreState();

            updateStatus(isCollecting ? 'Reprise de la collecte...' : 'Prêt à collecter');
            updateProgress();
        } catch (error) {
            updateStatus('Erreur d\'initialisation (voir console).');
        }
    }

    function saveState() {
        const state = {
            isCollecting: isCollecting,
            currentProject: currentProject,
            chapterQueue: chapterQueue,
            collectedData: collectedData,
            currentChapterIndex: currentChapterIndex,
            totalChapters: totalChapters
        };

        try {
            if (typeof GM_setValue !== 'undefined') {
                GM_setValue('manhwa-link-exporter-state', JSON.stringify(state));
            } else {
                localStorage.setItem('manhwa-link-exporter-state', JSON.stringify(state));
            }
        } catch (error) {
            // Silently fail if state cannot be saved
        }
    }

    function restoreState() {
        try {
            let savedState;
            if (typeof GM_getValue !== 'undefined') {
                savedState = GM_getValue('manhwa-link-exporter-state');
            } else {
                savedState = localStorage.getItem('manhwa-link-exporter-state');
            }

            if (savedState) {
                const state = JSON.parse(savedState);
                isCollecting = state.isCollecting || false;
                currentProject = state.currentProject || '';
                chapterQueue = state.chapterQueue || [];
                collectedData = state.collectedData || { chapters: {} }; // S'assurer que chapters est initialisé
                currentChapterIndex = state.currentChapterIndex || 0;
                totalChapters = state.totalChapters || 0;

                if (isCollecting && chapterQueue.length > 0) {
                    updateStatus('Reprise de la collecte...');
                    setTimeout(() => processChapterQueue(), CONFIG.pageLoadDelay);
                } else if (isCollecting) {
                    isCollecting = false;
                    clearState();
                }
            }
        } catch (error) {
            clearState();
        }
    }

    function clearState() {
        try {
            if (typeof GM_deleteValue !== 'undefined') {
                GM_deleteValue('manhwa-link-exporter-state');
            } else {
                localStorage.removeItem('manhwa-link-exporter-state');
            }
        } catch (error) {
            // Silently fail if state cannot be cleared
        }
    }

    function setupEventHandlers() {
        const saveBeforeUnload = () => {
            if (isCollecting) {
                saveState();
            }
        };

        window.addEventListener('beforeunload', saveBeforeUnload);
        window.addEventListener('pagehide', saveBeforeUnload);

        window.addEventListener('error', (event) => {
            if (event.message.includes('Extension context invalidated')) {
                return true;
            }
        });
    }

    setupEventHandlers();
    setTimeout(init, 50);

})();