// ==UserScript==
// @name         Manhwa Image Link Console Exporter
// @namespace    http://tampermonkey.net/
// @version      1.7
// @description  Collecte les liens d'images de manhwa/manga par chapitre et les affiche dans la console.
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
        projectTitleSelector: 'h1.project__content-informations-title',
        chapterListSelector: 'a.project__chapter.unstyled-link',
        imageSelector: 'img.chapter-image',
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
    let collectedData = {};
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
        if (!collectedData[chapterKey]) {
            collectedData[chapterKey] = {
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
                    collectedData[chapterKey].images.push(...imageUrls);
                    updateStatus(`Chapitre ${chapterNumber}: ${collectedData[chapterKey].images.length} images collectées.`);
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
        while (chapterQueue.length > 0 && isCollecting) {
            const chapterData = chapterQueue.shift();
            currentChapterIndex = totalChapters - chapterQueue.length;

            await collectChapterImages(chapterData.url, chapterData.number, chapterData.text);

            if (chapterQueue.length > 0) {
                await new Promise(resolve => setTimeout(resolve, CONFIG.delayBetweenChapters));
            }
        }

        if (isCollecting) {
            updateStatus('Collecte terminée. Affichage dans la console...');
            isCollecting = false;
            displayCollectedDataInConsole();
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

    // --- NEW FUNCTION TO DISPLAY IN CONSOLE ---
    function displayCollectedDataInConsole() {
        const projectName = getProjectName();
        console.groupCollapsed(`📚 Liens d'images pour le projet: ${projectName}`);
        console.log(JSON.stringify(collectedData, null, 2));
        console.groupEnd();
        console.log(`✅ Les liens d'images pour "${projectName}" ont été affichés dans la console.`);
    }

    function createUI() {
        const ui = document.createElement('div');
        ui.id = 'manhwa-link-exporter-ui';
        ui.innerHTML = `
            <div style="
                position: fixed;
                top: 20px;
                right: 20px;
                background: #2c3e50;
                color: white;
                padding: 15px;
                border-radius: 10px;
                z-index: 10000;
                min-width: 300px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                font-size: 14px;
                line-height: 1.5;
            ">
                <h3 style="margin: 0 0 10px 0; color: #ecf0f1;">🔗 Manhwa Link Exporter</h3>
                <div style="margin-bottom: 10px; font-size: 11px; color: #bdc3c7;">
                    Domaine: <span style="font-weight: bold;">${window.location.hostname}</span>
                </div>
                <div id="status" style="margin-bottom: 10px; color: #e0e0e0;">Prêt à collecter</div>
                <div id="progress-bar" style="
                    width: 100%;
                    height: 10px;
                    background: #34495e;
                    border-radius: 5px;
                    margin: 10px 0;
                    overflow: hidden;
                    display: none;
                ">
                    <div id="progress-fill" style="
                        height: 100%;
                        background: #3498db;
                        width: 0%;
                        transition: width 0.3s ease;
                    "></div>
                </div>
                <div style="margin-top: 10px; display: flex; justify-content: space-between;">
                    <button id="start-collection" style="
                        background: #27ae60;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        cursor: pointer;
                        flex-grow: 1;
                        margin-right: 5px;
                        font-size: 14px;
                    ">Démarrer Collecte</button>
                    <button id="stop-collection" style="
                        background: #e74c3c;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 5px;
                        cursor: pointer;
                        flex-grow: 1;
                        margin-left: 5px;
                        font-size: 14px;
                    ">Arrêter</button>
                </div>
                <div style="margin-top: 10px; display: flex; justify-content: space-between;">
                    <button id="test-selectors" style="
                        background: #f39c12;
                        color: white;
                        border: none;
                        padding: 6px 12px;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 12px;
                        flex-grow: 1;
                        margin-right: 5px;
                    ">Test Sélecteurs</button>
                    <button id="collect-current" style="
                        background: #9b59b6;
                        color: white;
                        border: none;
                        padding: 6px 12px;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 12px;
                        flex-grow: 1;
                        margin-left: 5px;
                    ">Collecter Page Actuelle</button>
                </div>
                <div style="margin-top: 10px; font-size: 12px; color: #bdc3c7;">
                    Projet: <span id="project-name" style="font-weight: bold; color: #ecf0f1;">${getProjectName()}</span>
                </div>
            </div>
        `;

        document.body.appendChild(ui);

        document.getElementById('start-collection').addEventListener('click', startCollection);
        document.getElementById('stop-collection').addEventListener('click', stopCollection);
        document.getElementById('test-selectors').addEventListener('click', testSelectors);
        document.getElementById('collect-current').addEventListener('click', collectCurrentPage);
    }

    function updateProgress() {
        const progressBar = document.getElementById('progress-bar');
        const progressFill = document.getElementById('progress-fill');

        if (progressBar && progressFill) {
            if (totalChapters > 0) {
                const percentage = ((totalChapters - chapterQueue.length) / totalChapters * 100).toFixed(1);
                progressBar.style.display = 'block';
                progressFill.style.width = percentage + '%';
            } else {
                progressBar.style.display = 'none';
            }
        }
    }

    async function collectCurrentPage() {
        if (isCollecting) {
            updateStatus('Une collecte est déjà en cours.');
            return;
        }

        isCollecting = true;
        currentProject = getProjectName();
        collectedData = {};
        chapterQueue = [];
        currentChapterIndex = 0;
        totalChapters = 1;

        updateStatus(`Collecte de liens pour la page actuelle...`);

        try {
            const chapterNumber = extractChapterNumber(window.location.href, document.title);
            await collectChapterImages(window.location.href, chapterNumber, document.title);

            updateStatus(`Collecte de la page actuelle terminée! ${Object.values(collectedData).flat().length} liens collectés.`);
            displayCollectedDataInConsole();
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
        currentProject = getProjectName();
        collectedData = {};
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
                collectedData = state.collectedData || {};
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
                // This error is common with Tampermonkey when tabs are closed/reloaded.
                // It doesn't necessarily mean a critical script error.
                return true;
            }
        });
    }

    setupEventHandlers();
    setTimeout(init, 50);

})();