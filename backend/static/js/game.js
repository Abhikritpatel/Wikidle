/**
 * Wiki-dle front end.
 *
 * The server owns the graph and the answers. This script asks it for today's puzzle
 * (/api/puzzle), the links of the page the player is on (/api/links) and the result of
 * each click (/api/move), then renders the board and keeps progress in localStorage.
 */

const MAX_LISTED = 100;

const gameState = {
    date: "",
    startNode: "",
    targetNode: "",
    shortestPathLength: 0,
    currentPage: "",
    clicksUsed: 0,
    maxClicks: 7,
    clickHistory: [], // { page, distance, feedback: 'start'|'closer'|'further'|'same'|'victory' }
    isGameOver: false,
    hasWon: false,
    links: [],
    busy: false
};

let filteredLinks = [];
let activeIndex = -1;
let countdownTimer = null;

const $ = id => document.getElementById(id);
const el = {
    loading: $("loading-panel"),
    game: $("game-container"),
    dateBadge: $("game-date-badge"),
    start: $("start-display"),
    target: $("target-display"),
    optimal: $("optimal-path-indicator"),
    current: $("current-page-display"),
    clicksRow: $("clicks-row"),
    clicksLeft: $("clicks-left-counter"),
    pips: $("pips"),
    input: $("search-input"),
    clear: $("clear-search-btn"),
    list: $("dropdown-menu"),
    history: $("history-list"),
    helpBtn: $("help-btn"),
    help: $("help-modal"),
    startBtn: $("start-game-btn"),
    over: $("game-over-modal"),
    title: $("modal-title"),
    subtitle: $("modal-subtitle"),
    used: $("modal-clicks-used"),
    best: $("modal-optimal-clicks"),
    grid: $("modal-emoji-grid"),
    stats: $("modal-stats"),
    next: $("next-puzzle"),
    share: $("share-btn"),
    close: $("modal-close-btn"),
    showResult: $("show-result-btn")
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function localDateString() {
    const d = new Date();
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

function plural(n, word) {
    return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function store(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ }
}

function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

async function fetchLinks(page) {
    const res = await fetch(`/api/links?page=${encodeURIComponent(page)}`);
    if (!res.ok) throw new Error("Couldn't load the links for this article.");
    return (await res.json()).links;
}

function showError(message) {
    el.loading.className = "error";
    el.loading.textContent = "";
    const p = document.createElement("p");
    p.textContent = message;
    const b = document.createElement("button");
    b.className = "btn";
    b.type = "button";
    b.textContent = "Try again";
    b.addEventListener("click", () => window.location.reload());
    el.loading.append(p, b);
    el.loading.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function initGame() {
    try {
        const res = await fetch(`/api/puzzle?date=${localDateString()}`);
        if (!res.ok) throw new Error("Couldn't load today's puzzle.");
        const puzzle = await res.json();

        gameState.date = puzzle.date;
        gameState.startNode = puzzle.startNode;
        gameState.targetNode = puzzle.targetNode;
        gameState.shortestPathLength = puzzle.shortestPathLength;
        gameState.maxClicks = Math.max(7, puzzle.shortestPathLength + 4);

        let saved = null;
        try { saved = JSON.parse(read("wikidle_state") || "null"); } catch (e) { saved = null; }

        if (saved && saved.date === gameState.date) {
            Object.assign(gameState, {
                currentPage: saved.currentPage,
                clicksUsed: saved.clicksUsed,
                clickHistory: saved.clickHistory,
                isGameOver: saved.isGameOver,
                hasWon: saved.hasWon
            });
        } else {
            gameState.currentPage = gameState.startNode;
            gameState.clickHistory = [{ page: gameState.startNode, distance: puzzle.startDistance, feedback: "start" }];
            saveState();
        }

        gameState.links = gameState.isGameOver ? [] : await fetchLinks(gameState.currentPage);

        el.dateBadge.textContent = formatDate(gameState.date);
        el.start.textContent = gameState.startNode;
        el.target.textContent = gameState.targetNode;
        el.optimal.textContent = `${plural(gameState.shortestPathLength, "click")}`;
        setupEvents();
        render();

        el.loading.classList.add("hidden");
        el.game.classList.remove("hidden");

        if (gameState.isGameOver) {
            openOver();
        } else if (!read("wikidle_rules_viewed")) {
            el.help.showModal();
        }
    } catch (err) {
        console.error(err);
        showError(err.message || "Something went wrong loading the game.");
    }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function markFor(step) {
    switch (step.feedback) {
        case "closer": return ["closer", "▲ closer"];
        case "further": return ["further", "▼ further"];
        case "same": return ["same", "= same distance"];
        case "victory": return ["win", "Goal reached"];
        default: return ["same", "start"];
    }
}

function distanceText(d) {
    if (d === 0) return "this is the goal";
    if (d < 0) return "no known route to the goal";
    return `${plural(d, "link")} from the goal`;
}

function render() {
    el.current.textContent = gameState.currentPage;

    const left = gameState.maxClicks - gameState.clicksUsed;
    el.clicksLeft.textContent = left;
    el.clicksRow.classList.toggle("low", left <= 2 && !gameState.isGameOver);
    el.pips.textContent = "";
    for (let i = 0; i < gameState.maxClicks; i++) {
        const pip = document.createElement("span");
        pip.className = "pip" + (i < gameState.clicksUsed ? " used" : "");
        el.pips.appendChild(pip);
    }

    el.history.textContent = "";
    gameState.clickHistory.forEach((step, i) => {
        const li = document.createElement("li");
        const n = document.createElement("span");
        n.className = "n";
        n.textContent = i;
        const title = document.createElement("span");
        title.className = "title";
        title.textContent = step.page;
        const [cls, label] = markFor(step);
        const mark = document.createElement("span");
        mark.className = "mark " + cls;
        mark.textContent = label;
        const sub = document.createElement("span");
        sub.className = "sub";
        sub.textContent = distanceText(step.distance);
        li.append(n, title, mark, sub);
        el.history.appendChild(li);
    });

    el.showResult.classList.toggle("hidden", !gameState.isGameOver);
    if (gameState.isGameOver) {
        el.input.disabled = true;
        el.input.placeholder = gameState.hasWon ? "You reached the goal" : "You're out of clicks";
    }
}

// ---------------------------------------------------------------------------
// Link search
// ---------------------------------------------------------------------------

function openList(open) {
    el.list.classList.toggle("hidden", !open);
    el.input.setAttribute("aria-expanded", String(open));
}

function updateDropdown() {
    if (gameState.isGameOver) return;
    const q = el.input.value.trim().toLowerCase();
    filteredLinks = gameState.links.filter(l => l.toLowerCase().includes(q));
    // Matches that start with the query first, then the rest
    filteredLinks.sort((a, b) => {
        const as = a.toLowerCase().startsWith(q) ? 0 : 1;
        const bs = b.toLowerCase().startsWith(q) ? 0 : 1;
        return as - bs;
    });
    activeIndex = -1;
    el.list.textContent = "";

    if (!filteredLinks.length) {
        const li = document.createElement("li");
        li.className = "note";
        li.textContent = "No links on this page match.";
        el.list.appendChild(li);
        openList(true);
        return;
    }

    filteredLinks.slice(0, MAX_LISTED).forEach((link, i) => {
        const li = document.createElement("li");
        li.role = "option";
        li.id = "opt-" + i;
        li.dataset.index = i;
        li.textContent = link;
        li.addEventListener("mousedown", e => e.preventDefault());
        li.addEventListener("click", () => selectLink(link));
        el.list.appendChild(li);
    });
    if (filteredLinks.length > MAX_LISTED) {
        const li = document.createElement("li");
        li.className = "note";
        li.textContent = `${filteredLinks.length - MAX_LISTED} more. Keep typing to narrow it down.`;
        el.list.appendChild(li);
    }
    openList(true);
}

function highlight() {
    const items = el.list.querySelectorAll("[data-index]");
    items.forEach(li => li.setAttribute("aria-selected", "false"));
    if (activeIndex >= 0 && items[activeIndex]) {
        items[activeIndex].setAttribute("aria-selected", "true");
        items[activeIndex].scrollIntoView({ block: "nearest" });
        el.input.setAttribute("aria-activedescendant", items[activeIndex].id);
    } else {
        el.input.removeAttribute("aria-activedescendant");
    }
}

function onKeydown(e) {
    const count = Math.min(filteredLinks.length, MAX_LISTED);
    if (e.key === "ArrowDown" && count) {
        e.preventDefault();
        if (el.list.classList.contains("hidden")) updateDropdown();
        activeIndex = (activeIndex + 1) % count;
        highlight();
    } else if (e.key === "ArrowUp" && count) {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + count) % count;
        highlight();
    } else if (e.key === "Enter") {
        e.preventDefault();
        const pick = activeIndex >= 0 ? filteredLinks[activeIndex] : filteredLinks[0];
        if (pick) selectLink(pick);
    } else if (e.key === "Escape") {
        openList(false);
    }
}

// ---------------------------------------------------------------------------
// Moves
// ---------------------------------------------------------------------------

async function selectLink(page) {
    if (gameState.isGameOver || gameState.busy) return;
    gameState.busy = true;
    const previousDist = gameState.clickHistory[gameState.clickHistory.length - 1].distance;

    let dist, nextLinks;
    try {
        const q = `date=${encodeURIComponent(gameState.date)}&from=${encodeURIComponent(gameState.currentPage)}&to=${encodeURIComponent(page)}`;
        const res = await fetch(`/api/move?${q}`);
        if (!res.ok) throw new Error("Move rejected");
        dist = (await res.json()).distance;
        nextLinks = dist === 0 ? [] : await fetchLinks(page);
    } catch (err) {
        console.error(err);
        gameState.busy = false;
        el.input.placeholder = "Couldn't reach the server. Try again";
        return;
    }
    gameState.busy = false;

    gameState.links = nextLinks;
    gameState.currentPage = page;
    gameState.clicksUsed += 1;

    let feedback = "same";
    if (dist === 0) {
        feedback = "victory";
        gameState.isGameOver = true;
        gameState.hasWon = true;
    } else if (previousDist >= 0 && dist >= 0) {
        feedback = dist < previousDist ? "closer" : dist > previousDist ? "further" : "same";
    }
    gameState.clickHistory.push({ page, distance: dist, feedback });

    if (!gameState.hasWon && gameState.clicksUsed >= gameState.maxClicks) gameState.isGameOver = true;
    if (gameState.isGameOver) recordStats();
    saveState();

    el.input.value = "";
    el.clear.classList.add("hidden");
    openList(false);
    render();

    if (gameState.isGameOver) setTimeout(openOver, 500);
}

// ---------------------------------------------------------------------------
// End of game, sharing, stats
// ---------------------------------------------------------------------------

function loadStats() {
    const base = { played: 0, wins: 0, streak: 0, best: 0, lastDate: "" };
    try { return Object.assign(base, JSON.parse(read("wikidle_stats") || "{}")); } catch (e) { return base; }
}

function recordStats() {
    const st = loadStats();
    if (st.lastDate === gameState.date) return;
    st.played += 1;
    if (gameState.hasWon) {
        st.wins += 1;
        st.streak += 1;
        st.best = Math.max(st.best, st.streak);
    } else {
        st.streak = 0;
    }
    st.lastDate = gameState.date;
    store("wikidle_stats", JSON.stringify(st));
}

function shareText() {
    const head = gameState.hasWon
        ? `Wiki-dle ${gameState.date}\n${gameState.clicksUsed}/${gameState.maxClicks} clicks (shortest: ${gameState.shortestPathLength})`
        : `Wiki-dle ${gameState.date}\nX/${gameState.maxClicks} clicks (shortest: ${gameState.shortestPathLength})`;
    const squares = gameState.clickHistory.slice(1).map(s =>
        s.feedback === "closer" ? "🟩" : s.feedback === "further" ? "🟥" : s.feedback === "victory" ? "🏁" : "⬜");
    return `${head}\n${squares.join("")}`;
}

function startCountdown() {
    clearInterval(countdownTimer);
    const tick = () => {
        const now = new Date();
        const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
        const s = Math.max(0, Math.floor((next - now) / 1000));
        const pad = n => String(n).padStart(2, "0");
        el.next.textContent = `Next puzzle in ${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
        if (s === 0) window.location.reload();
    };
    tick();
    countdownTimer = setInterval(tick, 1000);
}

function openOver() {
    el.used.textContent = gameState.clicksUsed;
    el.best.textContent = gameState.shortestPathLength;
    if (gameState.hasWon) {
        el.title.textContent = "You made it";
        el.subtitle.textContent = gameState.clicksUsed === gameState.shortestPathLength
            ? "You found the shortest route."
            : `You reached ${gameState.targetNode} in ${plural(gameState.clicksUsed, "click")}.`;
    } else {
        el.title.textContent = "Out of clicks";
        el.subtitle.textContent = `The goal was ${gameState.targetNode}.`;
    }
    const st = loadStats();
    el.stats.textContent = `Played ${st.played} · Won ${st.wins} · Streak ${st.streak} · Best streak ${st.best}`;
    el.grid.textContent = shareText();
    startCountdown();
    if (!el.over.open) el.over.showModal();
}

async function copyResult() {
    const text = `${shareText()}\n${window.location.origin}`;
    const original = el.share.textContent;
    try {
        await navigator.clipboard.writeText(text);
        el.share.textContent = "Copied";
    } catch (e) {
        el.share.textContent = "Select the result above to copy";
    }
    setTimeout(() => { el.share.textContent = original; }, 2000);
}

// ---------------------------------------------------------------------------
// State and events
// ---------------------------------------------------------------------------

function saveState() {
    store("wikidle_state", JSON.stringify({
        date: gameState.date,
        currentPage: gameState.currentPage,
        clicksUsed: gameState.clicksUsed,
        clickHistory: gameState.clickHistory,
        isGameOver: gameState.isGameOver,
        hasWon: gameState.hasWon
    }));
}

function setupEvents() {
    el.input.addEventListener("input", () => {
        el.clear.classList.toggle("hidden", !el.input.value);
        updateDropdown();
    });
    el.input.addEventListener("focus", updateDropdown);
    el.input.addEventListener("keydown", onKeydown);
    el.clear.addEventListener("click", () => {
        el.input.value = "";
        el.clear.classList.add("hidden");
        el.input.focus();
        updateDropdown();
    });
    document.addEventListener("click", e => {
        if (!e.target.closest(".search")) openList(false);
    });

    el.helpBtn.addEventListener("click", () => el.help.showModal());
    el.startBtn.addEventListener("click", () => {
        el.help.close();
        store("wikidle_rules_viewed", "1");
    });
    el.help.addEventListener("close", () => store("wikidle_rules_viewed", "1"));

    el.share.addEventListener("click", copyResult);
    el.close.addEventListener("click", () => el.over.close());
    el.showResult.addEventListener("click", openOver);
}

window.addEventListener("DOMContentLoaded", initGame);
