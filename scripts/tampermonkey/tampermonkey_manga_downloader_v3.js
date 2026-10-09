// ==UserScript==
// @name         Manga Downloader v3 — analyse auto + téléchargement
// @namespace    manhwa-project
// @version      3.0
// @description  Analyse la page (titre, liste des chapitres, images), devine les sélecteurs et télécharge les chapitres en CBR/CBZ — ou exporte le JSON des scripts hyperspeed.
// @match        *://*/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @grant        GM_xmlhttpRequest
// @grant        GM_download
// @grant        GM_registerMenuCommand
// @connect      *
// @run-at       document-idle
// @noframes
// ==/UserScript==

/*
 * Fonctionnement
 *  1. Analyse : sur une page de série, repère le titre et le groupe de liens qui
 *     forme la liste des chapitres (liens au même modèle d'URL avec des numéros
 *     différents). Puis ouvre un chapitre en arrière-plan pour repérer les images
 *     de lecture (le plus grand groupe d'images de même structure), ou à défaut les
 *     URL d'images présentes dans les scripts de la page (sites Next.js, Madara…).
 *  2. Les sélecteurs trouvés s'affichent, sont modifiables et peuvent être
 *     enregistrés pour le site (ils sont alors réutilisés à chaque visite).
 *  3. Téléchargement : pour chaque chapitre coché, récupère les images (avec le
 *     Referer du chapitre), les met dans un CBR/CBZ (ZIP sans compression) et
 *     l'enregistre dans Téléchargements/<Titre>/<Titre> - Chapitre 001.cbr.
 *     Les chapitres déjà téléchargés sont mémorisés et peuvent être ignorés.
 *     Le format JSON produit le fichier attendu par watch_downloads.py / hyperspeed.
 *
 * Dossier par série : Tampermonkey → Paramètres (mode avancé) → Téléchargements BETA →
 *   « Mode de téléchargement : API du navigateur » et ajouter cbr, cbz, json aux extensions
 *   autorisées. Sinon les fichiers arrivent directement dans Téléchargements.
 */

(function () {
    'use strict';

    if (window.__mangaDownloaderV3) return;
    window.__mangaDownloaderV3 = true;

    // ------------------------------------------------------------------ //
    // Réglages
    // ------------------------------------------------------------------ //

    const OPT = {
        imageConcurrency: 4,
        delayBetweenChapters: 800,
        retries: 3,
        iframeTimeout: 15000,
    };
    const SITE_KEY = 'cfg:' + location.host;
    const BAD_IMG = /logo|avatar|icon|emoji|banner|sprite|favicon|loading|placeholder|blank\.gif|spacer|pixel|badge|discord|facebook|twitter|patreon|kofi|\/ads?[\/_.-]/i;
    const CHAP_KW = /(?<![a-z])(?:chap(?:ter|itre)?|ch|episode|ep|eps)[\s._\/-]*0*(\d+(?:[.,]\d+)?)/i;
    const IMG_IN_TEXT = /https?:\/\/[^"'\s<>()\\]+?\.(?:jpe?g|png|webp|avif|gif)(?:\?[^"'\s<>\\]*)?/gi;

    // ------------------------------------------------------------------ //
    // Utilitaires
    // ------------------------------------------------------------------ //

    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const store = {
        get: (k, d) => { try { const v = GM_getValue(k); return v === undefined ? d : JSON.parse(v); } catch (e) { return d; } },
        set: (k, v) => { try { GM_setValue(k, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } },
        del: k => { try { GM_deleteValue(k); } catch (e) { /* idem */ } },
    };
    const safeFile = s => (s || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim()
        .replace(/[. ]+$/, '').slice(0, 150) || 'Manga';
    const projectName = s => (s || 'manga').toLowerCase().replace(/[^a-z0-9]/g, '_');
    const pad = (n, w = 3) => { const [a, b] = String(n).split('.'); return a.padStart(w, '0') + (b ? '.' + b : ''); };
    const fmtB = n => n < 1048576 ? (n / 1024).toFixed(0) + ' Ko' : (n / 1048576).toFixed(1) + ' Mo';
    const absUrl = (u, base) => { try { return new URL(u, base).href; } catch (e) { return null; } };

    function chapterNumber(url, text) {
        const t = (text || '').replace(/\s+/g, ' ');
        let m = t.match(CHAP_KW) || decodeURIComponent((url || '').split(/[?#]/)[0]).match(CHAP_KW);
        if (m) return String(parseFloat(m[1].replace(',', '.')));
        const tn = t.match(/\d+(?:\.\d+)?/g);
        if (tn && tn.length === 1) return String(parseFloat(tn[0]));
        const un = (url || '').split(/[?#]/)[0].match(/\d+(?:\.\d+)?/g);
        return un ? String(parseFloat(un[un.length - 1])) : null;
    }

    /** Texte d'un élément avec un espace entre chaque balise (« Chapter 60 » + « 4 weeks ago » ≠ « Chapter 604 weeks ago »). */
    function nodeText(el) {
        const parts = [];
        const w = (el.ownerDocument || document).createTreeWalker(el, NodeFilter.SHOW_TEXT);
        for (let n = w.nextNode(); n; n = w.nextNode()) parts.push(n.nodeValue);
        return parts.join(' ').replace(/\s+/g, ' ').trim();
    }

    /** Retire les dates relatives (« 4 weeks ago », « il y a 2 jours », « 18 hours »…). */
    const DATE_UNITS = '(?:sec(?:ond)?e?s?|min(?:ute)?s?|h(?:ou)?rs?|heures?|days?|jours?|weeks?|semaines?|months?|mois|years?|ans?)';
    const stripDate = s => s
        .replace(new RegExp(`\\bil y a\\s+(?:\\d+|une?)\\s*${DATE_UNITS}\\b`, 'gi'), '')
        .replace(new RegExp(`\\b(?:\\d+|an?)\\s*${DATE_UNITS}\\s+ago\\b`, 'gi'), '')
        .replace(new RegExp(`\\s\\d+\\s*${DATE_UNITS}\\s*$`, 'i'), '')
        .replace(/\b(?:yesterday|today|hier|aujourd'hui)\b/gi, '')
        .replace(/\b\d{1,4}[\/.-]\d{1,2}[\/.-]\d{1,4}\b|\b(?:jan|feb|fév|mar|apr|avr|may|mai|jun|juin|jul|juil|aug|août|sep|oct|nov|dec|déc)[a-zé]*\.?\s+\d{1,2},?\s+\d{4}\b/gi, '')
        .replace(/\s+/g, ' ').replace(/[\s·•|-]+$/, '').trim();

    /** Modèle d'URL : les segments de chemin contenant un chiffre deviennent {n}. */
    function urlSignature(u) {
        try {
            const x = new URL(u, location.href);
            const path = x.pathname.replace(/\/+$/, '').split('/').map(s => /\d/.test(s) ? '{n}' : s).join('/');
            const keys = [...x.searchParams.keys()].sort().join('&');
            return x.host + path + (keys ? '?' + keys : '');
        } catch (e) { return ''; }
    }

    function stableClasses(el) {
        return [...el.classList].filter(c => /^[a-zA-Z_-][\w-]*$/.test(c) && c.length < 40
            && !/\d{3,}|^(css|sc|jsx|svelte|emotion|chakra)-|^_/.test(c)).slice(0, 3);
    }
    function selPart(el) {
        if (el.id && /^[a-zA-Z][\w-]*$/.test(el.id) && !/\d{3,}/.test(el.id)) return '#' + CSS.escape(el.id);
        return el.tagName.toLowerCase() + stableClasses(el).map(c => '.' + CSS.escape(c)).join('');
    }
    /** Sélecteur CSS générique (sans :nth-child) d'un élément, sur quelques niveaux. */
    function cssPath(el, depth = 4) {
        const parts = [];
        for (let e = el, i = 0; e && e.nodeType === 1 && e.tagName !== 'HTML' && i < depth; e = e.parentElement, i++) {
            const p = selPart(e);
            parts.unshift(p);
            if (p.startsWith('#') || e.tagName === 'BODY') break;
        }
        return parts.join(' > ');
    }
    function commonAncestor(els) {
        let a = els[0].parentElement;
        while (a && !els.every(e => a.contains(e))) a = a.parentElement;
        return a || els[0].ownerDocument.body;
    }
    function qsa(doc, sel) { try { return [...doc.querySelectorAll(sel)]; } catch (e) { return []; } }

    function imgUrl(img, base) {
        for (const a of ['data-src', 'data-lazy-src', 'data-original', 'data-url', 'data-cfsrc', 'data-srcset', 'src', 'srcset']) {
            let v = (img.getAttribute(a) || '').trim();
            if (!v || v.startsWith('data:')) continue;
            if (a.endsWith('srcset')) v = v.split(',')[0].trim().split(/\s+/)[0];
            const u = absUrl(v, base);
            if (u && /^https?:/.test(u)) return u;
        }
        return null;
    }
    const dirOf = u => u.replace(/[?#].*$/, '').replace(/[^/]*$/, '');

    // ------------------------------------------------------------------ //
    // Analyse
    // ------------------------------------------------------------------ //

    /** Cherche le groupe de liens qui ressemble le plus à une liste de chapitres. */
    function detectChapters(doc, base) {
        const groups = new Map();
        for (const a of doc.querySelectorAll('a[href]')) {
            const href = absUrl(a.getAttribute('href'), base);
            if (!href || !/^https?:/.test(href) || href.split('#')[0] === base.split('#')[0]) continue;
            const sig = urlSignature(href);
            if (!sig.includes('{n}') && !sig.includes('?')) continue;
            if (!groups.has(sig)) groups.set(sig, []);
            groups.get(sig).push(a);
        }
        let best = null;
        for (const [sig, els] of groups) {
            const nums = new Set(els.map(a => chapterNumber(a.href || a.getAttribute('href'), nodeText(a))).filter(Boolean));
            const kw = els.some(a => CHAP_KW.test(a.getAttribute('href')) || CHAP_KW.test(nodeText(a)));
            const score = nums.size * (kw ? 3 : 1);
            if (nums.size >= 2 && (!best || score > best.score)) best = { sig, els, score };
        }
        if (!best) return null;
        return { chapterSelector: cssPath(commonAncestor(best.els), 4) + ' a[href]', chapterSignature: best.sig };
    }

    function getChapters(doc, base, cfg) {
        if (!cfg.chapterSelector && !cfg.chapterSignature) return [];  // rien de détecté : pas tous les liens de la page
        let els = cfg.chapterSelector ? qsa(doc, cfg.chapterSelector) : [];
        if (!els.length) els = qsa(doc, 'a[href]');
        const byUrl = new Map();
        for (const a of els) {
            const url = absUrl(a.getAttribute('href'), base);
            if (!url || (cfg.chapterSignature && urlSignature(url) !== cfg.chapterSignature)) continue;
            const raw = nodeText(a);
            const text = stripDate(raw).slice(0, 90) || raw.slice(0, 90);
            const prev = byUrl.get(url);
            if (!prev || text.length > prev.text.length) byUrl.set(url, { url, text, num: chapterNumber(url, raw) });
        }
        return [...byUrl.values()].sort((a, b) => (a.num === null) - (b.num === null)
            || parseFloat(a.num) - parseFloat(b.num) || a.text.localeCompare(b.text));
    }

    const stripTitle = s => (s || '').replace(/\s+/g, ' ').trim()
        .replace(/\s*[-–|:]?\s*(chap(ter|itre)?|ch\.?|episode|ep\.?)\s*\d+.*$/i, '').trim();

    function detectTitle(doc) {
        const strip = stripTitle;
        const h1 = doc.querySelector('h1');
        if (h1 && strip(h1.textContent).length >= 2 && h1.textContent.length < 200) {
            return { title: strip(h1.textContent), titleSelector: cssPath(h1, 3) };
        }
        const og = doc.querySelector('meta[property="og:title"]');
        const t = strip((og && og.content) || doc.title).split(/\s+[|–-]\s+/)[0];
        return { title: t || location.host, titleSelector: '' };
    }

    /** Images de lecture : le plus grand groupe d'images de même structure et même dossier. */
    function detectImages(doc, base) {
        const groups = new Map();
        for (const img of doc.querySelectorAll('img')) {
            const u = imgUrl(img, base);
            if (!u || BAD_IMG.test(u) || !img.parentElement) continue;
            if (doc === document && img.complete && img.naturalWidth && img.naturalWidth < 200) continue;
            const key = cssPath(img.parentElement, 3);
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(u);
        }
        let best = null;
        for (const [key, urls] of groups) {
            const uniq = [...new Set(urls)];
            const dirs = {};
            uniq.forEach(u => { dirs[dirOf(u)] = (dirs[dirOf(u)] || 0) + 1; });
            const score = Math.max(...Object.values(dirs));
            if (uniq.length >= 2 && (!best || score > best.score)) best = { key, uniq, score };
        }
        if (best) return { imageMode: 'selector', imageSelector: best.key + ' > img', imagePrefix: '', urls: best.uniq };
        const s = scriptImages(doc, '');
        if (s.urls.length >= 2) return { imageMode: 'script', imageSelector: '', imagePrefix: s.prefix, urls: s.urls };
        return null;
    }

    /** URL d'images écrites dans les scripts (JSON Next.js, ts_reader, etc.). */
    function scriptImages(doc, prefix) {
        const text = [...doc.querySelectorAll('script')].map(s => s.textContent).join('\n').replace(/\\\//g, '/');
        const all = [...new Set((text.match(IMG_IN_TEXT) || []).filter(u => !BAD_IMG.test(u)))];
        if (prefix) return { prefix, urls: all.filter(u => u.startsWith(prefix)) };
        const dirs = {};
        all.forEach(u => { dirs[dirOf(u)] = (dirs[dirOf(u)] || 0) + 1; });
        const top = Object.entries(dirs).sort((a, b) => b[1] - a[1])[0];
        return top ? { prefix: top[0], urls: all.filter(u => dirOf(u) === top[0]) } : { prefix: '', urls: [] };
    }

    function extractImages(doc, base, cfg) {
        if (cfg.imageMode === 'script') return scriptImages(doc, cfg.imagePrefix).urls;
        if (cfg.imageSelector) {
            const urls = [...new Set(qsa(doc, cfg.imageSelector).map(i => imgUrl(i, base)).filter(Boolean))];
            if (urls.length) return urls;
        }
        const d = detectImages(doc, base);
        return d ? d.urls : [];
    }

    // ------------------------------------------------------------------ //
    // Réseau
    // ------------------------------------------------------------------ //

    function gmRequest(url, opts) {
        return new Promise((resolve, reject) => GM_xmlhttpRequest({
            method: 'GET', url, timeout: 60000, ...opts,
            onload: r => (r.status >= 200 && r.status < 300) ? resolve(r) : reject(new Error('HTTP ' + r.status)),
            onerror: () => reject(new Error('réseau')),
            ontimeout: () => reject(new Error('délai dépassé')),
        }));
    }

    async function withRetry(fn, label) {
        let err;
        for (let i = 1; i <= OPT.retries; i++) {
            try { return await fn(); } catch (e) { err = e; await sleep(1000 * i * i); }
        }
        throw new Error(`${label} : ${err && err.message}`);
    }

    async function fetchDoc(url) {
        const html = await withRetry(async () => {
            if (new URL(url).origin === location.origin) {
                const r = await fetch(url, { credentials: 'include' });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.text();
            }
            return (await gmRequest(url, { headers: { Referer: location.href } })).responseText;
        }, 'page');
        return new DOMParser().parseFromString(html, 'text/html');
    }

    /** Charge un chapitre dans une iframe cachée (sites qui construisent la page en JavaScript). */
    function iframeImages(url, cfg) {
        return new Promise(resolve => {
            if (new URL(url).origin !== location.origin) return resolve([]);
            const f = document.createElement('iframe');
            f.style.cssText = 'position:fixed;left:-10000px;top:0;width:1000px;height:900px;border:0;visibility:hidden';
            f.src = url;
            let last = -1, stable = 0;
            const t0 = Date.now();
            const tick = setInterval(() => {
                let urls = [];
                try { urls = extractImages(f.contentDocument, url, cfg); } catch (e) { /* pas encore prêt */ }
                stable = urls.length && urls.length === last ? stable + 1 : 0;
                last = urls.length;
                if (stable >= 3 || Date.now() - t0 > OPT.iframeTimeout) {
                    clearInterval(tick); f.remove(); resolve(urls);
                }
            }, 500);
            document.body.appendChild(f);
        });
    }

    async function chapterImages(ch, cfg) {
        if (ch.url.split('#')[0] === location.href.split('#')[0]) return extractImages(document, location.href, cfg);
        const doc = await fetchDoc(ch.url);
        let urls = extractImages(doc, ch.url, cfg);
        if (!urls.length) urls = await iframeImages(ch.url, cfg);
        return urls;
    }

    async function fetchImage(url, referer) {
        const r = await withRetry(() => gmRequest(url, { responseType: 'arraybuffer', headers: { Referer: referer } }), 'image');
        const type = (/content-type:\s*([^\r\n;]+)/i.exec(r.responseHeaders) || [])[1] || '';
        let ext = (type.split('/')[1] || '').replace('jpeg', 'jpg');
        if (!/^(jpg|png|webp|gif|avif)$/.test(ext)) ext = ((/\.(jpe?g|png|webp|gif|avif)(?:[?#]|$)/i.exec(url) || [])[1] || 'jpg').toLowerCase().replace('jpeg', 'jpg');
        return { data: new Uint8Array(r.response), ext };
    }

    async function pool(items, n, fn) {
        let i = 0;
        await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
            while (i < items.length) { const k = i++; await fn(items[k], k); }
        }));
    }

    // ------------------------------------------------------------------ //
    // ZIP (CBR/CBZ) sans compression
    // ------------------------------------------------------------------ //

    const CRC_TABLE = (() => {
        const t = new Uint32Array(256);
        for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
        return t;
    })();
    function crc32(u8) {
        let c = 0xFFFFFFFF;
        for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 255] ^ (c >>> 8);
        return (c ^ 0xFFFFFFFF) >>> 0;
    }
    function makeZip(files) {
        const enc = new TextEncoder(), parts = [], central = [];
        const d = new Date();
        const time = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
        const date = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
        let offset = 0, cdSize = 0;
        for (const f of files) {
            const name = enc.encode(f.name), crc = crc32(f.data), size = f.data.length;
            const lh = new DataView(new ArrayBuffer(30));
            lh.setUint32(0, 0x04034b50, true); lh.setUint16(4, 20, true); lh.setUint16(6, 0x0800, true);
            lh.setUint16(10, time, true); lh.setUint16(12, date, true); lh.setUint32(14, crc, true);
            lh.setUint32(18, size, true); lh.setUint32(22, size, true); lh.setUint16(26, name.length, true);
            parts.push(lh.buffer, name, f.data);
            const ch = new DataView(new ArrayBuffer(46));
            ch.setUint32(0, 0x02014b50, true); ch.setUint16(4, 20, true); ch.setUint16(6, 20, true);
            ch.setUint16(8, 0x0800, true); ch.setUint16(12, time, true); ch.setUint16(14, date, true);
            ch.setUint32(16, crc, true); ch.setUint32(20, size, true); ch.setUint32(24, size, true);
            ch.setUint16(28, name.length, true); ch.setUint32(42, offset, true);
            central.push(ch.buffer, name);
            offset += 30 + name.length + size;
            cdSize += 46 + name.length;
        }
        const end = new DataView(new ArrayBuffer(22));
        end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
        end.setUint32(12, cdSize, true); end.setUint32(16, offset, true);
        return new Blob([...parts, ...central, end.buffer], { type: 'application/zip' });
    }

    function anchorDownload(blob, file) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = file;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    /** Enregistre dans Téléchargements/<dossier>/<fichier> (ou à plat si Tampermonkey refuse). */
    function saveBlob(blob, folder, file) {
        return new Promise(resolve => {
            const fallback = () => { anchorDownload(blob, file); resolve(false); };
            if (typeof GM_download !== 'function') return fallback();
            try { GM_download({
                url: blob, name: folder ? `${folder}/${file}` : file, saveAs: false,
                onload: () => resolve(true),
                onerror: fallback,
                ontimeout: fallback,
            }); } catch (e) { fallback(); }
        });
    }

    // ------------------------------------------------------------------ //
    // État
    // ------------------------------------------------------------------ //

    const seriesKey = () => 'done:' + location.host + location.pathname.replace(/\/+$/, '');
    let cfg = {}, chapters = [], selected = new Set(), pageType = 'none', running = false, paused = false, stopReq = false;
    const doneSet = () => new Set(store.get(seriesKey(), []));
    const markDone = url => { const s = doneSet(); s.add(url); store.set(seriesKey(), [...s]); };

    function analyze(useSaved = true) {
        const saved = useSaved ? store.get(SITE_KEY, null) : null;
        const t = detectTitle(document);
        const auto = detectChapters(document, location.href) || {};
        cfg = { title: t.title, titleSelector: t.titleSelector, chapterSelector: auto.chapterSelector || '',
                chapterSignature: auto.chapterSignature || '', imageMode: 'selector', imageSelector: '', imagePrefix: '' };
        if (saved) {
            Object.assign(cfg, saved);
            if (saved.titleSelector) {
                const el = qsa(document, saved.titleSelector)[0];
                if (el && stripTitle(el.textContent)) cfg.title = stripTitle(el.textContent);
            }
        }
        chapters = getChapters(document, location.href, cfg);
        if (saved && !chapters.length && auto.chapterSelector) {  // sélecteurs enregistrés périmés
            Object.assign(cfg, auto);
            chapters = getChapters(document, location.href, cfg);
        }
        const live = detectImages(document, location.href);
        const onChapter = (cfg.chapterSignature && urlSignature(location.href) === cfg.chapterSignature)
            || (CHAP_KW.test(location.pathname) && live && live.urls.length >= 3);
        if (onChapter && live && !saved) Object.assign(cfg, { imageMode: live.imageMode, imageSelector: live.imageSelector, imagePrefix: live.imagePrefix });
        pageType = onChapter ? 'chapter' : chapters.length >= 2 ? 'series' : 'none';
        if (onChapter && !chapters.some(c => c.url.split('#')[0] === location.href.split('#')[0])) {
            chapters.push({ url: location.href, text: 'Cette page', num: chapterNumber(location.href, document.title) });
        }
        const done = doneSet();
        selected = new Set(onChapter ? [location.href] : chapters.filter(c => !done.has(c.url)).map(c => c.url));
        return pageType;
    }

    /** Ouvre un chapitre en arrière-plan pour deviner le sélecteur d'images. */
    async function sampleImages() {
        const ch = chapters.find(c => selected.has(c.url)) || chapters[0];
        if (!ch) return null;
        setStatus(`Analyse des images sur « ${ch.text || ch.url} »…`);
        if (cfg.imageSelector || cfg.imagePrefix) {  // sélecteur déjà connu (enregistré ou saisi)
            const urls = await chapterImages(ch, cfg);
            if (urls.length) return { ch, urls };
        }
        const doc = ch.url.split('#')[0] === location.href.split('#')[0] ? document : await fetchDoc(ch.url);
        const d = detectImages(doc, ch.url);
        if (d) {
            Object.assign(cfg, { imageMode: d.imageMode, imageSelector: d.imageSelector, imagePrefix: d.imagePrefix });
            return { ch, urls: d.urls };
        }
        return { ch, urls: await iframeImages(ch.url, { imageMode: 'selector', imageSelector: '' }) };
    }

    // ------------------------------------------------------------------ //
    // Téléchargement
    // ------------------------------------------------------------------ //

    async function runDownload() {
        const format = ui.$('#fmt').value;
        const skip = ui.$('#skip').checked;
        const done = doneSet();
        const list = chapters.filter(c => selected.has(c.url) && !(skip && format !== 'json' && done.has(c.url)));
        if (!list.length) return setStatus('Aucun chapitre à télécharger.');
        const title = safeFile(ui.$('#title').value || cfg.title);
        const width = Math.max(3, ...list.map(c => String(Math.floor(parseFloat(c.num) || 0)).length));
        const json = { projectName: projectName(title), chapters: {} };
        running = true; stopReq = false; paused = false; renderButtons();
        const errors = [];
        let bytes = 0;

        for (let ci = 0; ci < list.length && !stopReq; ci++) {
            while (paused && !stopReq) await sleep(300);
            if (stopReq) break;
            const ch = list[ci];
            const label = ch.num !== null ? `Chapitre ${pad(ch.num, width)}` : safeFile(ch.text);
            setProgress(ci / list.length, `${ci + 1}/${list.length} · ${label} : recherche des images…`);
            try {
                const urls = await chapterImages(ch, cfg);
                if (!urls.length) throw new Error('aucune image trouvée (vérifie le sélecteur d\'images)');
                if (format === 'json') {
                    json.chapters[`Chapitre ${ch.num ?? ci + 1} - ${ch.text}`] = { url: ch.url, images: urls };
                } else {
                    const files = new Array(urls.length);
                    let n = 0;
                    await pool(urls, OPT.imageConcurrency, async (u, k) => {
                        const img = await fetchImage(u, ch.url);
                        files[k] = { name: `page_${String(k + 1).padStart(3, '0')}.${img.ext}`, data: img.data };
                        bytes += img.data.length;
                        setProgress((ci + ++n / urls.length) / list.length,
                            `${ci + 1}/${list.length} · ${label} : image ${n}/${urls.length} · ${fmtB(bytes)}`);
                    });
                    const inFolder = await saveBlob(makeZip(files), title, `${title} - ${label}.${format}`);
                    if (!inFolder && ci === 0) log('ℹ Fichiers enregistrés sans sous-dossier (voir réglages Tampermonkey en tête du script).');
                    markDone(ch.url);
                }
                log(`✓ ${label} — ${urls.length} images`);
            } catch (e) {
                errors.push(label);
                log(`✕ ${label} — ${e.message}`);
            }
            if (ci < list.length - 1) await sleep(OPT.delayBetweenChapters);
        }

        if (format === 'json' && Object.keys(json.chapters).length) {
            anchorDownload(new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' }), `${json.projectName}.json`);
            log(`✓ JSON exporté : ${json.projectName}.json`);
        }
        running = false; renderButtons(); renderList();
        setProgress(1, stopReq ? 'Arrêté.' : errors.length ? `Terminé avec ${errors.length} erreur(s) : ${errors.join(', ')}` : `Terminé ✓ ${list.length} chapitre(s)`);
    }

    // ------------------------------------------------------------------ //
    // Interface (Shadow DOM : le style du site n'interfère pas)
    // ------------------------------------------------------------------ //

    const CSS_TXT = `
    :host{all:initial}
    *{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
    .fab{position:fixed;right:18px;bottom:18px;z-index:2147483646;width:52px;height:52px;border-radius:16px;border:0;cursor:pointer;
      background:linear-gradient(135deg,#ff5d8f,#7c6cff);color:#fff;font-size:24px;box-shadow:0 8px 28px #0007}
    .panel{position:fixed;right:18px;bottom:82px;z-index:2147483647;width:420px;max-width:calc(100vw - 24px);max-height:calc(100vh - 110px);
      overflow:auto;background:#141821f2;backdrop-filter:blur(12px);color:#e8ebf2;border:1px solid #2a3142;border-radius:16px;
      box-shadow:0 20px 60px #000a;font-size:13px;line-height:1.4;display:none}
    .panel.on{display:block}
    header{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid #2a3142;position:sticky;top:0;background:#141821}
    header b{flex:1;font-size:14px}
    .badge{padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600;background:#ffffff14;color:#8b93a7}
    .b-ok{background:#3ddc9722;color:#3ddc97}.b-acc{background:#ff5d8f22;color:#ff5d8f}
    section{padding:10px 14px;border-bottom:1px solid #2a314288}
    label{display:block;color:#8b93a7;font-size:11.5px;margin:6px 0 3px}
    input[type=text],input[type=number],select{width:100%;background:#0d0f14;color:#e8ebf2;border:1px solid #2a3142;border-radius:8px;padding:7px 9px;font-size:12.5px;outline:none}
    input.mono{font-family:Consolas,monospace;font-size:11.5px}
    input:focus,select:focus{border-color:#7c6cff}
    button{background:#1f2533;color:#e8ebf2;border:1px solid #2a3142;border-radius:8px;padding:6px 10px;font-size:12px;font-weight:600;cursor:pointer}
    button:hover:not(:disabled){border-color:#56607a}
    button:disabled{opacity:.45;cursor:not-allowed}
    .primary{background:linear-gradient(135deg,#ff5d8f,#e04bb0);border:0}
    .x{background:none;border:0;color:#8b93a7;font-size:16px}
    .row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:6px}
    .row > input{flex:1;min-width:0}
    details summary{cursor:pointer;color:#a79dff;font-weight:600;margin-bottom:4px}
    .list{max-height:220px;overflow:auto;border:1px solid #2a3142;border-radius:8px;margin-top:6px}
    .ch{display:flex;gap:8px;align-items:center;padding:5px 8px;border-bottom:1px solid #ffffff08;cursor:pointer}
    .ch span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .ch.done span{color:#3ddc97}
    .mut{color:#8b93a7;font-size:11.5px}
    .thumbs{display:flex;gap:6px;margin-top:6px}.thumbs img{width:60px;height:84px;object-fit:cover;border-radius:6px;background:#0d0f14}
    .bar{height:7px;border-radius:9px;background:#0005;overflow:hidden;margin:8px 0 6px}
    .bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7c6cff,#ff5d8f);transition:width .3s}
    .log{max-height:120px;overflow:auto;font-family:Consolas,monospace;font-size:11px;color:#8b93a7;margin-top:6px;white-space:pre-wrap}
    `;

    const HTML = `
    <button class="fab" id="fab" title="Manga Downloader v3">📥</button>
    <div class="panel" id="panel">
      <header><b>Manga Downloader v3</b><span class="badge" id="type"></span><button class="x" id="close">✕</button></header>
      <section>
        <label>Titre de la série (nom du dossier et des fichiers)</label>
        <input type="text" id="title">
      </section>
      <section>
        <details id="det"><summary>Sélecteurs détectés</summary>
          <label>Titre</label><input type="text" class="mono" id="sTitle">
          <label>Liens des chapitres</label><input type="text" class="mono" id="sChap">
          <label>Modèle d'URL des chapitres ({n} = numéro)</label><input type="text" class="mono" id="sSig">
          <label>Images — sélecteur CSS (ou vide + préfixe pour les images trouvées dans les scripts)</label>
          <input type="text" class="mono" id="sImg">
          <label>Préfixe d'URL des images (mode scripts)</label><input type="text" class="mono" id="sPrefix">
          <div class="row">
            <button id="reanalyze">Réanalyser</button><button id="apply">Appliquer</button>
            <button id="hl">Surligner</button><button id="test">Tester les images</button>
          </div>
          <div class="row"><button id="save">Enregistrer pour ce site</button><button id="forget">Oublier</button>
            <span class="mut" id="savedSt"></span></div>
        </details>
        <div class="mut" id="sample"></div><div class="thumbs" id="thumbs"></div>
      </section>
      <section>
        <div class="row" style="margin:0"><b id="count" style="flex:1"></b>
          <button id="all">Tous</button><button id="none">Aucun</button><button id="notdone">Non téléchargés</button></div>
        <div class="row"><input type="number" id="from" placeholder="Du n°" step="any"><input type="number" id="to" placeholder="au n°" step="any"><button id="range">Cocher</button></div>
        <div class="list" id="list"></div>
      </section>
      <section>
        <div class="row" style="margin:0">
          <select id="fmt" style="flex:1"><option value="cbr">CBR (images dans un ZIP)</option><option value="cbz">CBZ</option>
            <option value="json">JSON (scripts hyperspeed)</option></select>
          <label style="display:flex;gap:5px;align-items:center;margin:0"><input type="checkbox" id="skip" checked> ignorer déjà téléchargés</label>
        </div>
        <div class="row"><button class="primary" id="go" style="flex:1">Télécharger</button><button id="pause">Pause</button><button id="stop">Arrêter</button></div>
        <div class="bar"><i id="bar"></i></div>
        <div class="mut" id="status"></div>
        <div class="log" id="log"></div>
      </section>
    </div>`;

    const ui = {};

    function buildUI() {
        const host = document.createElement('div');
        host.id = 'manga-downloader-v3';
        const root = host.attachShadow({ mode: 'open' });
        root.innerHTML = `<style>${CSS_TXT}</style>${HTML}`;
        document.documentElement.appendChild(host);
        ui.root = root;
        ui.$ = s => root.querySelector(s);

        ui.$('#fab').onclick = () => togglePanel();
        ui.$('#close').onclick = () => togglePanel(false);
        ui.$('#reanalyze').onclick = () => { analyze(false); fillCfg(); renderAll(); autoSample(); };
        ui.$('#apply').onclick = () => { readCfg(); chapters = getChapters(document, location.href, cfg); selected = new Set(chapters.map(c => c.url)); renderAll(); };
        ui.$('#hl').onclick = highlight;
        ui.$('#test').onclick = () => { readCfg(); autoSample(true); };
        ui.$('#save').onclick = () => { readCfg(); const { title, ...sel } = cfg; store.set(SITE_KEY, sel); renderSaved(); setStatus('Sélecteurs enregistrés pour ' + location.host); };
        ui.$('#forget').onclick = () => { store.del(SITE_KEY); renderSaved(); setStatus('Sélecteurs oubliés pour ' + location.host); };
        ui.$('#all').onclick = () => { chapters.forEach(c => selected.add(c.url)); renderList(); };
        ui.$('#none').onclick = () => { selected.clear(); renderList(); };
        ui.$('#notdone').onclick = () => { const d = doneSet(); selected = new Set(chapters.filter(c => !d.has(c.url)).map(c => c.url)); renderList(); };
        ui.$('#range').onclick = () => {
            const a = parseFloat(ui.$('#from').value), b = parseFloat(ui.$('#to').value);
            selected = new Set(chapters.filter(c => { const n = parseFloat(c.num); return !isNaN(n) && (isNaN(a) || n >= a) && (isNaN(b) || n <= b); }).map(c => c.url));
            renderList();
        };
        ui.$('#list').onclick = e => {
            const row = e.target.closest('.ch'); if (!row) return;
            const u = row.dataset.u;
            selected.has(u) ? selected.delete(u) : selected.add(u);
            renderList();
        };
        ui.$('#go').onclick = () => { if (!running) { ui.$('#log').textContent = ''; readCfg(); runDownload(); } };
        ui.$('#pause').onclick = () => { paused = !paused; renderButtons(); setStatus(paused ? 'En pause…' : 'Reprise…'); };
        ui.$('#stop').onclick = () => { stopReq = true; paused = false; setStatus('Arrêt après le chapitre en cours…'); };
    }

    function togglePanel(force) {
        const p = ui.$('#panel');
        const on = force === undefined ? !p.classList.contains('on') : force;
        p.classList.toggle('on', on);
    }

    function fillCfg() {
        ui.$('#title').value = cfg.title || '';
        ui.$('#sTitle').value = cfg.titleSelector || '';
        ui.$('#sChap').value = cfg.chapterSelector || '';
        ui.$('#sSig').value = cfg.chapterSignature || '';
        ui.$('#sImg').value = cfg.imageMode === 'script' ? '' : (cfg.imageSelector || '');
        ui.$('#sPrefix').value = cfg.imageMode === 'script' ? (cfg.imagePrefix || '') : '';
    }
    function readCfg() {
        cfg.title = ui.$('#title').value.trim() || cfg.title;
        cfg.titleSelector = ui.$('#sTitle').value.trim();
        cfg.chapterSelector = ui.$('#sChap').value.trim();
        cfg.chapterSignature = ui.$('#sSig').value.trim();
        cfg.imageSelector = ui.$('#sImg').value.trim();
        cfg.imagePrefix = ui.$('#sPrefix').value.trim();
        cfg.imageMode = !cfg.imageSelector && cfg.imagePrefix ? 'script' : 'selector';
    }

    function renderSaved() { ui.$('#savedSt').textContent = store.get(SITE_KEY, null) ? '✓ enregistré pour ce site' : ''; }
    function renderAll() {
        const t = { series: ['Page série', 'b-ok'], chapter: ['Page chapitre', 'b-acc'], none: ['Rien détecté', ''] }[pageType];
        ui.$('#type').textContent = t[0]; ui.$('#type').className = 'badge ' + t[1];
        renderSaved(); renderList(); renderButtons();
    }
    function renderList() {
        const d = doneSet();
        ui.$('#count').textContent = `${selected.size} / ${chapters.length} chapitre(s) coché(s)`;
        ui.$('#list').innerHTML = chapters.length ? chapters.map(c => `<div class="ch ${d.has(c.url) ? 'done' : ''}" data-u="${c.url.replace(/"/g, '&quot;')}">
            <input type="checkbox" ${selected.has(c.url) ? 'checked' : ''}><span title="${c.url.replace(/"/g, '&quot;')}">${c.num !== null ? 'n°' + c.num + ' — ' : ''}${c.text.replace(/</g, '&lt;') || c.url}</span>
            ${d.has(c.url) ? '<span class="badge b-ok" style="flex:none">✓</span>' : ''}</div>`).join('')
            : '<div class="ch"><span class="mut">Aucun chapitre détecté — ajuste les sélecteurs puis « Appliquer ».</span></div>';
        renderButtons();
    }
    function renderButtons() {
        ui.$('#go').disabled = running || !selected.size;
        ui.$('#go').textContent = running ? 'Téléchargement…' : `Télécharger (${selected.size})`;
        ui.$('#pause').disabled = ui.$('#stop').disabled = !running;
        ui.$('#pause').textContent = paused ? 'Reprendre' : 'Pause';
    }
    function setStatus(m) { ui.$('#status').textContent = m; }
    function setProgress(f, m) { ui.$('#bar').style.width = (Math.min(1, f) * 100).toFixed(1) + '%'; setStatus(m); }
    function log(m) { const l = ui.$('#log'); l.textContent += m + '\n'; l.scrollTop = l.scrollHeight; console.log('[Manga v3]', m); }

    function highlight() {
        readCfg();
        const els = qsa(document, cfg.chapterSelector).filter(a => !cfg.chapterSignature || urlSignature(a.href) === cfg.chapterSignature);
        const imgs = cfg.imageSelector ? qsa(document, cfg.imageSelector) : [];
        const t = qsa(document, cfg.titleSelector).slice(0, 1);
        const mark = (list, color) => list.forEach(e => { e.dataset.mdOutline = e.style.outline; e.style.outline = `3px solid ${color}`; });
        mark(t, '#3ddc97'); mark(els, '#ff5d8f'); mark(imgs, '#7c6cff');
        setStatus(`Surligné : titre ${t.length ? '✓' : '✕'} (vert) · ${els.length} liens de chapitres (rose) · ${imgs.length} images (violet)`);
        if (els[0]) els[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
        setTimeout(() => [...t, ...els, ...imgs].forEach(e => { e.style.outline = e.dataset.mdOutline || ''; }), 5000);
    }

    async function autoSample(force) {
        if (!chapters.length) return;
        if (!force && (cfg.imageSelector || cfg.imagePrefix) && pageType !== 'series') return;
        try {
            const r = await sampleImages();
            fillCfg();
            if (!r || !r.urls.length) {
                ui.$('#sample').textContent = 'Images introuvables automatiquement — renseigne le sélecteur d\'images puis « Tester les images ».';
                ui.$('#thumbs').innerHTML = ''; ui.$('#det').open = true;
                return setStatus('');
            }
            ui.$('#sample').textContent = `Échantillon « ${r.ch.text || r.ch.url} » : ${r.urls.length} images (${cfg.imageMode === 'script' ? 'trouvées dans les scripts' : 'sélecteur CSS'})`;
            ui.$('#thumbs').innerHTML = '';
            r.urls.slice(0, 4).forEach(u => {
                const im = document.createElement('img');
                im.referrerPolicy = 'no-referrer-when-downgrade'; im.src = u; im.title = u;
                ui.$('#thumbs').appendChild(im);
            });
            setStatus('Analyse terminée. Vérifie les sélecteurs puis télécharge.');
        } catch (e) {
            ui.$('#sample').textContent = 'Échantillon impossible : ' + e.message;
        }
    }

    // ------------------------------------------------------------------ //
    // Démarrage
    // ------------------------------------------------------------------ //

    let built = false;
    function open(show) {
        if (!built) { buildUI(); built = true; }
        fillCfg(); renderAll();
        if (show) togglePanel(true);
    }

    function start() {
        analyze();
        if (pageType !== 'none' || store.get(SITE_KEY, null)) { open(false); autoSample(); }
    }

    if (typeof GM_registerMenuCommand === 'function') {
        GM_registerMenuCommand('📥 Ouvrir Manga Downloader v3', () => { analyze(); open(true); autoSample(); });
    }
    start();
    // Sites qui chargent la liste des chapitres après coup (SPA)
    setTimeout(() => { if (!built || !chapters.length) start(); }, 3000);
})();
