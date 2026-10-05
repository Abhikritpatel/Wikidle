/**
 * Wiki-dle - Frontend Game Engine & State Machine
 * 
 * This file manages the client-side game state, handles fetching the daily puzzle 
 * and localized graph, implements the keyboard-navigable autocomplete search dropdown,
 * computes O(1) proximity feedback based on pre-computed distances, and persists
 * game state in local storage.
 * 
 * Game State Machine:
 * - INIT: Fetch graph and puzzle. Restore state from localStorage if date matches.
 * - PLAYING: Accept user search input, filter outgoing links, and process clicks.
 * - GAME_OVER: Trigger Victory/Defeat modal, disable input, generate share grid.
 */

// Global Game State
let gameState = {
    date: "",
    startNode: "",
    targetNode: "",
    shortestPathLength: 0,
    currentPage: "",
    clicksUsed: 0,
    maxClicks: 7,
    clickHistory: [], // Array of { page: string, distance: number, feedback: 'start'|'warmer'|'colder'|'same'|'victory' }
    isGameOver: false,
    hasWon: false,
    links: [],       // Outgoing links of the current page (from /api/links)
    busy: false      // True while a move is being validated by the server
};

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function localDateString() {
    const d = new Date();
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

async function fetchLinks(page) {
    const res = await fetch(`/api/links?page=${encodeURIComponent(page)}`);
    if (!res.ok) throw new Error("Could not load links for " + page);
    return (await res.json()).links;
}

// Autocomplete State
let activeDropdownIndex = -1;
let filteredLinks = [];

// DOM Elements
const elements = {
    loadingPanel: document.getElementById("loading-panel"),
    gameContainer: document.getElementById("game-container"),
    currentPageDisplay: document.getElementById("current-page-display"),
    targetPageDisplay: document.getElementById("target-page-display"),
    clicksLeftCounter: document.getElementById("clicks-left-counter"),
    optimalPathIndicator: document.getElementById("optimal-path-indicator"),
    searchInput: document.getElementById("search-input"),
    dropdownMenu: document.getElementById("dropdown-menu"),
    clearSearchBtn: document.getElementById("clear-search-btn"),
    historyList: document.getElementById("history-list"),
    helpBtn: document.getElementById("help-btn"),
    helpModal: document.getElementById("help-modal"),
    closeHelpBtn: document.getElementById("close-help-btn"),
    startGameBtn: document.getElementById("start-game-btn"),
    gameOverModal: document.getElementById("game-over-modal"),
    modalTitle: document.getElementById("modal-title"),
    modalSubtitle: document.getElementById("modal-subtitle"),
    modalClicksUsed: document.getElementById("modal-clicks-used"),
    modalOptimalClicks: document.getElementById("modal-optimal-clicks"),
    modalEmojiGrid: document.getElementById("modal-emoji-grid"),
    shareBtn: document.getElementById("share-btn"),
    modalCloseBtn: document.getElementById("modal-close-btn"),
    modalIcon: document.getElementById("modal-icon"),
    modalIconContainer: document.getElementById("modal-icon-container"),
    modalGlow: document.getElementById("modal-glow"),
    resetGameBtn: document.getElementById("reset-game-btn")
};

// -------------------------------------------------------------------------
// 1. Initializers & Data Fetching
// -------------------------------------------------------------------------

/**
 * Entry point for the game. Fetches required JSON files and initializes state.
 */
async function initGame() {
    try {
        // 1. Fetch today's puzzle (using the player's local date)
        const puzzleResponse = await fetch(`/api/puzzle?date=${localDateString()}`);
        if (!puzzleResponse.ok) {
            throw new Error("Failed to load today's puzzle. Please try again.");
        }
        const puzzleData = await puzzleResponse.json();

        // 2. Initialize state
        gameState.date = puzzleData.date;
        gameState.startNode = puzzleData.startNode;
        gameState.targetNode = puzzleData.targetNode;
        gameState.shortestPathLength = puzzleData.shortestPathLength;
        const dateBadge = document.getElementById("game-date-badge");
        if (dateBadge) dateBadge.textContent = gameState.date;

        // Dynamic max clicks based on shortest path: optimal path + 4 extra clicks
        gameState.maxClicks = Math.max(7, puzzleData.shortestPathLength + 4);

        // 3. Check LocalStorage to restore active daily session
        const savedState = loadStateFromLocalStorage();
        if (savedState && savedState.date === gameState.date) {
            // Restore saved session
            gameState.currentPage = savedState.currentPage;
            gameState.clicksUsed = savedState.clicksUsed;
            gameState.clickHistory = savedState.clickHistory;
            gameState.isGameOver = savedState.isGameOver;
            gameState.hasWon = savedState.hasWon;
        } else {
            // New game session
            gameState.currentPage = gameState.startNode;
            gameState.clicksUsed = 0;
            gameState.isGameOver = false;
            gameState.hasWon = false;
            gameState.clickHistory = [{
                page: gameState.startNode,
                distance: puzzleData.startDistance,
                feedback: 'start'
            }];
            saveStateToLocalStorage();
        }

        // 4. Load the links of the current page, then render
        gameState.links = await fetchLinks(gameState.currentPage);
        renderBoard();
        setupEventListeners();

        // Reveal game board
        elements.loadingPanel.classList.add("hidden");
        elements.gameContainer.classList.remove("hidden");

        // If restored state is already game over, trigger the modal
        if (gameState.isGameOver) {
            triggerGameOverModal();
        } else {
            // Show help modal for first-time daily players
            if (!localStorage.getItem("wikidle_rules_viewed")) {
                toggleHelpModal(true);
            }
        }

    } catch (error) {
        console.error("Initialization error:", error);
        elements.loadingPanel.innerHTML = `
            <div class="text-center p-6 bg-red-950/20 border border-red-900/30 rounded-2xl max-w-md mx-auto">
                <i class="fa-solid fa-triangle-exclamation text-red-500 text-3xl mb-3"></i>
                <h3 class="heading-font text-lg font-bold text-white">Initialization Failed</h3>
                <p class="text-xs text-slate-400 mt-1">${escapeHtml(error.message)}</p>
                <button onclick="window.location.reload()" class="mt-4 bg-red-800 hover:bg-red-700 text-white font-bold py-2 px-4 rounded-xl text-xs transition-colors">
                    Retry Loading
                </button>
            </div>
        `;
    }
}

// -------------------------------------------------------------------------
// 2. UI Rendering Engine
// -------------------------------------------------------------------------

/**
 * Updates all DOM elements with the current game state.
 */
function renderBoard() {
    // 1. HUD Updates
    elements.currentPageDisplay.textContent = gameState.currentPage;
    elements.targetPageDisplay.textContent = gameState.targetNode;
    
    const clicksRemaining = gameState.maxClicks - gameState.clicksUsed;
    elements.clicksLeftCounter.textContent = clicksRemaining;
    elements.clicksLeftCounter.className = `text-3xl font-black heading-font ${
        clicksRemaining <= 2 ? 'text-red-400 animate-pulse' : clicksRemaining <= 4 ? 'text-amber-400' : 'text-emerald-400'
    }`;

    elements.optimalPathIndicator.textContent = `${gameState.shortestPathLength} clicks optimal`;

    // 2. Render Path Timeline
    elements.historyList.innerHTML = "";
    
    gameState.clickHistory.forEach((step, index) => {
        const item = document.createElement("div");
        item.className = "relative flex items-start group";

        // Feedback styling mapper
        let badgeColor = "bg-slate-800 text-slate-400 border-slate-700";
        let badgeIcon = "fa-circle-notch";
        let feedbackText = "Start Article";

        if (step.feedback === 'warmer') {
            badgeColor = "bg-orange-950/40 text-orange-400 border-orange-800/40";
            badgeIcon = "fa-fire";
            feedbackText = "Getting Warmer";
        } else if (step.feedback === 'colder') {
            badgeColor = "bg-cyan-950/40 text-cyan-400 border-cyan-800/40";
            badgeIcon = "fa-snowflake";
            feedbackText = "Getting Colder";
        } else if (step.feedback === 'same') {
            badgeColor = "bg-slate-950/60 text-slate-400 border-slate-800/40";
            badgeIcon = "fa-equals";
            feedbackText = "Same Distance";
        } else if (step.feedback === 'victory') {
            badgeColor = "bg-emerald-950/40 text-emerald-400 border-emerald-800/40";
            badgeIcon = "fa-trophy";
            feedbackText = "Target Reached!";
        }

        const distanceText = step.distance === 0 ? "Goal!" : step.distance === -1 ? "Unknown" : `${step.distance} click${step.distance > 1 ? 's' : ''} away`;

        item.innerHTML = `
            <!-- Step index marker -->
            <span class="absolute -left-[33px] top-1.5 flex items-center justify-center w-5 h-5 rounded-full border-2 bg-slate-950 text-[9px] font-bold ${
                step.feedback === 'victory' ? 'border-emerald-500 text-emerald-400' : 'border-violet-950 text-slate-500'
            }">
                ${index}
            </span>
            
            <!-- Step Card Content -->
            <div class="glass-panel w-full rounded-xl p-4 flex justify-between items-center glass-panel-hover ml-2">
                <div class="space-y-1">
                    <h4 class="font-bold text-sm text-white line-clamp-1">${escapeHtml(step.page)}</h4>
                    <div class="flex items-center space-x-2">
                        <span class="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${badgeColor} flex items-center space-x-1">
                            <i class="fa-solid ${badgeIcon} text-[8px]"></i>
                            <span>${feedbackText}</span>
                        </span>
                        <span class="text-xs text-slate-500">${distanceText}</span>
                    </div>
                </div>
                ${index > 0 ? `
                    <div class="text-right text-xs font-semibold text-slate-500">
                        Step ${index}
                    </div>
                ` : ''}
            </div>
        `;
        
        // Prepend so latest clicks are at the top, or append?
        // Since we are building a vertical timeline, appending reads top-to-bottom.
        // Let's append, which reads chronologically down, and auto-scroll the container.
        elements.historyList.appendChild(item);
    });

    // Auto-scroll to the bottom of the timeline so the player sees their latest step
    window.scrollTo({
        top: document.body.scrollHeight,
        behavior: 'smooth'
    });

    // 3. Disable inputs if Game Over
    if (gameState.isGameOver) {
        elements.searchInput.disabled = true;
        elements.searchInput.placeholder = gameState.hasWon 
            ? "Victory! You reached the target." 
            : "Game Over! Out of clicks.";
        elements.searchInput.classList.add("bg-slate-950/40", "border-slate-900", "text-slate-500");
    }
}

// -------------------------------------------------------------------------
// 3. Autocomplete Search Dropdown
// -------------------------------------------------------------------------

/**
 * Filters the outgoing links for the current page based on the search query
 * and renders them in the floating dropdown list.
 */
function updateDropdown() {
    const query = elements.searchInput.value.trim().toLowerCase();
    
    // Get valid outgoing links for the current page from G
    const outgoingLinks = gameState.links;
    
    // Filter outgoing links based on search query (substring match)
    filteredLinks = outgoingLinks.filter(link => 
        link.toLowerCase().includes(query)
    );

    elements.dropdownMenu.innerHTML = "";
    activeDropdownIndex = -1;

    if (filteredLinks.length === 0) {
        elements.dropdownMenu.innerHTML = `
            <div class="px-4 py-3 text-xs text-slate-500 italic flex items-center space-x-2">
                <i class="fa-solid fa-circle-exclamation"></i>
                <span>No matching outgoing links on this page.</span>
            </div>
        `;
        elements.dropdownMenu.classList.remove("hidden");
        return;
    }

    // Render filtered links as clickable list items
    filteredLinks.forEach((link, index) => {
        const item = document.createElement("div");
        item.className = "px-4 py-3 text-sm text-slate-200 cursor-pointer hover:bg-brand-600 hover:text-white transition-colors border-b border-violet-950/20 last:border-b-0 flex justify-between items-center";
        item.dataset.index = index;
        
        // Show distance preview? No, that would be cheating!
        // Just show page name and navigation arrow icon
        item.innerHTML = `
            <span class="font-medium truncate pr-4">${escapeHtml(link)}</span>
            <i class="fa-solid fa-chevron-right text-[10px] text-slate-500 hover-arrow"></i>
        `;

        item.addEventListener("click", () => {
            selectLink(link);
        });

        elements.dropdownMenu.appendChild(item);
    });

    elements.dropdownMenu.classList.remove("hidden");
}

/**
 * Navigates the dropdown list using keyboard arrow keys.
 */
function handleDropdownKeyboardNav(e) {
    const items = elements.dropdownMenu.querySelectorAll("[data-index]");
    if (items.length === 0) return;

    if (e.key === "ArrowDown") {
        e.preventDefault();
        activeDropdownIndex = (activeDropdownIndex + 1) % items.length;
        highlightDropdownItem(items);
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeDropdownIndex = (activeDropdownIndex - 1 + items.length) % items.length;
        highlightDropdownItem(items);
    } else if (e.key === "Enter") {
        e.preventDefault();
        if (activeDropdownIndex >= 0 && activeDropdownIndex < filteredLinks.length) {
            selectLink(filteredLinks[activeDropdownIndex]);
        } else if (filteredLinks.length > 0) {
            // Default to first item if Enter pressed without arrow nav
            selectLink(filteredLinks[0]);
        }
    } else if (e.key === "Escape") {
        closeDropdown();
    }
}

/**
 * Highlights a specific item in the dropdown.
 */
function highlightDropdownItem(items) {
    items.forEach(item => {
        item.classList.remove("bg-brand-600", "text-white");
        item.classList.add("text-slate-200");
    });

    if (activeDropdownIndex >= 0) {
        const activeItem = items[activeDropdownIndex];
        activeItem.classList.add("bg-brand-600", "text-white");
        activeItem.classList.remove("text-slate-200");
        
        // Ensure highlighted item is scrolled into view inside the dropdown
        activeItem.scrollIntoView({ block: "nearest" });
    }
}

/**
 * Closes the floating dropdown.
 */
function closeDropdown() {
    elements.dropdownMenu.classList.add("hidden");
    activeDropdownIndex = -1;
}

// -------------------------------------------------------------------------
// 4. Core Game Loop & State Updates
// -------------------------------------------------------------------------

/**
 * Processes navigation to a selected page, updates state, and checks for game over.
 * Time Complexity: O(1) distance checks.
 * 
 * @param {string} selectedPage - Canonical title of the selected page.
 */
async function selectLink(selectedPage) {
    if (gameState.isGameOver || gameState.busy) return;
    gameState.busy = true;

    // 1. Ask the server to validate the move and give the distance to the target
    const previousPage = gameState.currentPage;
    const previousDist = gameState.clickHistory[gameState.clickHistory.length - 1].distance;
    let currentDist, newLinks;
    try {
        const res = await fetch(`/api/move?date=${encodeURIComponent(gameState.date)}&from=${encodeURIComponent(previousPage)}&to=${encodeURIComponent(selectedPage)}`);
        if (!res.ok) throw new Error("Move rejected");
        currentDist = (await res.json()).distance;
        newLinks = currentDist === 0 ? [] : await fetchLinks(selectedPage);
    } catch (err) {
        console.error(err);
        gameState.busy = false;
        elements.searchInput.placeholder = "Network error - try again";
        return;
    }
    gameState.busy = false;
    gameState.links = newLinks;

    // 2. Increment clicks used
    gameState.currentPage = selectedPage;
    gameState.clicksUsed += 1;

    // 3. Determine Proximity Feedback (Warmer / Colder / Same / Victory)
    let feedback = 'same';
    if (currentDist === 0) {
        feedback = 'victory';
        gameState.isGameOver = true;
        gameState.hasWon = true;
    } else if (previousDist === -1 || currentDist === -1) {
        feedback = 'same'; // Fallback if distances are somehow missing
    } else if (currentDist < previousDist) {
        feedback = 'warmer';
    } else if (currentDist > previousDist) {
        feedback = 'colder';
    } else {
        feedback = 'same';
    }

    // 4. Append to history list
    gameState.clickHistory.push({
        page: selectedPage,
        distance: currentDist,
        feedback: feedback
    });

    // 5. Check Defeat Condition
    if (gameState.clicksUsed >= gameState.maxClicks && !gameState.hasWon) {
        gameState.isGameOver = true;
    }

    if (gameState.isGameOver) recordStats();

    // 6. Persist state in localStorage
    saveStateToLocalStorage();

    // 7. Clear search bar and close dropdown
    elements.searchInput.value = "";
    elements.clearSearchBtn.classList.add("hidden");
    closeDropdown();

    // 8. Re-render UI
    renderBoard();

    // 9. If game has ended, show modal
    if (gameState.isGameOver) {
        setTimeout(triggerGameOverModal, 600); // Slight delay for premium feel
    }
}

// -------------------------------------------------------------------------
// 5. Game Over & Share Mechanics
// -------------------------------------------------------------------------

/**
 * Renders stats and generates a shareable emoji path in the Game Over modal.
 */
function triggerGameOverModal() {
    elements.modalClicksUsed.textContent = gameState.clicksUsed;
    elements.modalOptimalClicks.textContent = gameState.shortestPathLength;

    if (gameState.hasWon) {
        // Victory styling
        elements.modalTitle.textContent = "Victory!";
        elements.modalTitle.className = "heading-font text-2xl font-black text-emerald-400 glow-text";
        elements.modalSubtitle.textContent = `You navigated the Wikipedia maze in ${gameState.clicksUsed} clicks!`;
        
        elements.modalIcon.className = "fa-solid fa-trophy text-emerald-400 animate-subtle-bounce";
        elements.modalIconContainer.className = "mx-auto w-16 h-16 rounded-full bg-emerald-950/50 border border-emerald-500/30 flex items-center justify-center text-3xl shadow-lg shadow-emerald-500/15";
        elements.modalGlow.className = "absolute -top-24 left-1/2 -translate-x-1/2 w-48 h-48 rounded-full bg-emerald-500/10 blur-3xl";
        elements.gameOverModal.firstElementChild.className = "glass-panel max-w-md w-full rounded-2xl p-6 text-center relative shadow-2xl overflow-hidden border-2 border-emerald-500/20";
    } else {
        // Defeat styling
        elements.modalTitle.textContent = "Crashed!";
        elements.modalTitle.className = "heading-font text-2xl font-black text-red-400 glow-text";
        elements.modalSubtitle.textContent = `You ran out of clicks. The target was ${gameState.targetNode}.`;
        
        elements.modalIcon.className = "fa-solid fa-skull-crossbones text-red-400";
        elements.modalIconContainer.className = "mx-auto w-16 h-16 rounded-full bg-red-950/50 border border-red-500/30 flex items-center justify-center text-3xl shadow-lg shadow-red-500/15";
        elements.modalGlow.className = "absolute -top-24 left-1/2 -translate-x-1/2 w-48 h-48 rounded-full bg-red-500/10 blur-3xl";
        elements.gameOverModal.firstElementChild.className = "glass-panel max-w-md w-full rounded-2xl p-6 text-center relative shadow-2xl overflow-hidden border-2 border-red-500/20";
    }

    const statsEl = document.getElementById("modal-stats");
    if (statsEl) {
        const st = loadStats();
        statsEl.textContent = `Played ${st.played} · Wins ${st.wins} · Streak ${st.streak} · Best streak ${st.best}`;
    }

    // Generate Shareable Emoji Grid
    const emojiGrid = generateEmojiGrid();
    elements.modalEmojiGrid.innerHTML = emojiGrid.replace(/\n/g, "<br>");

    // Show modal
    elements.gameOverModal.classList.remove("hidden");
}

/**
 * Builds the Wordle-style text layout with emojis.
 * @return {string}
 */
function generateEmojiGrid() {
    let text = `Wiki-dle 📅 ${gameState.date}\n`;
    
    if (gameState.hasWon) {
        text += `Score: ${gameState.clicksUsed}/${gameState.maxClicks} clicks (Optimal: ${gameState.shortestPathLength})\n`;
    } else {
        text += `Result: Crashed 💥 (${gameState.clicksUsed}/${gameState.maxClicks} clicks)\n`;
    }

    text += `🎬 ➔ `;
    
    // Map click history to emojis
    // Start page is step 0, skipped in history feedback rendering
    const feedbackEmojis = gameState.clickHistory.slice(1).map(step => {
        if (step.feedback === 'warmer') return '🔥';
        if (step.feedback === 'colder') return '❄️';
        if (step.feedback === 'victory') return '🎉';
        return '◽';
    });

    text += feedbackEmojis.join(' ➔ ');
    return text;
}

/**
 * Copies the share text to the user's clipboard.
 */
function copyShareText() {
    const gridText = generateEmojiGrid() + `\nPlay at: ${window.location.origin}`;
    
    navigator.clipboard.writeText(gridText)
        .then(() => {
            const originalText = elements.shareBtn.innerHTML;
            elements.shareBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>Copied to Clipboard!</span>`;
            elements.shareBtn.classList.remove("from-brand-600", "to-fuchsia-600");
            elements.shareBtn.classList.add("bg-emerald-600");
            
            setTimeout(() => {
                elements.shareBtn.innerHTML = originalText;
                elements.shareBtn.classList.add("from-brand-600", "to-fuchsia-600");
                elements.shareBtn.classList.remove("bg-emerald-600");
            }, 2000);
        })
        .catch(err => {
            console.error("Failed to copy share text:", err);
            alert("Failed to copy. Please manually copy the grid text.");
        });
}

// -------------------------------------------------------------------------
// 6. State Persistence (LocalStorage)
// -------------------------------------------------------------------------

function loadStats() {
    try {
        return Object.assign({ played: 0, wins: 0, streak: 0, best: 0, lastDate: "" },
            JSON.parse(localStorage.getItem("wikidle_stats") || "{}"));
    } catch (e) {
        return { played: 0, wins: 0, streak: 0, best: 0, lastDate: "" };
    }
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
    try { localStorage.setItem("wikidle_stats", JSON.stringify(st)); } catch (e) { /* storage unavailable */ }
}

/**
 * Saves current daily game progress to local storage.
 */
function saveStateToLocalStorage() {
    const stateToSave = {
        date: gameState.date,
        currentPage: gameState.currentPage,
        clicksUsed: gameState.clicksUsed,
        clickHistory: gameState.clickHistory,
        isGameOver: gameState.isGameOver,
        hasWon: gameState.hasWon
    };
    localStorage.setItem("wikidle_state", JSON.stringify(stateToSave));
}

/**
 * Loads and parses daily game progress from local storage.
 * @return {object|null}
 */
function loadStateFromLocalStorage() {
    try {
        const data = localStorage.getItem("wikidle_state");
        return data ? JSON.parse(data) : null;
    } catch (e) {
        console.warn("Failed to load state from localStorage:", e);
        return null;
    }
}

// -------------------------------------------------------------------------
// 7. Events & Overlay Toggles
// -------------------------------------------------------------------------

/**
 * Binds DOM events to game and autocomplete functions.
 */
function setupEventListeners() {
    // Autocomplete input hooks
    elements.searchInput.addEventListener("input", () => {
        if (elements.searchInput.value.trim().length > 0) {
            elements.clearSearchBtn.classList.remove("hidden");
        } else {
            elements.clearSearchBtn.classList.add("hidden");
        }
        updateDropdown();
    });

    // Reveal dropdown menu on input focus (excellent UX)
    elements.searchInput.addEventListener("focus", () => {
        updateDropdown();
    });

    // Keyboard navigation hooks
    elements.searchInput.addEventListener("keydown", handleDropdownKeyboardNav);

    // Clear search button hook
    elements.clearSearchBtn.addEventListener("click", () => {
        elements.searchInput.value = "";
        elements.clearSearchBtn.classList.add("hidden");
        elements.searchInput.focus();
        updateDropdown();
    });

    // Click outside to close dropdown
    document.addEventListener("click", (e) => {
        if (!elements.searchInput.contains(e.target) && !elements.dropdownMenu.contains(e.target)) {
            closeDropdown();
        }
    });

    // Help Modal Triggers
    elements.helpBtn.addEventListener("click", () => toggleHelpModal(true));
    elements.closeHelpBtn.addEventListener("click", () => toggleHelpModal(false));
    elements.startGameBtn.addEventListener("click", () => {
        toggleHelpModal(false);
        localStorage.setItem("wikidle_rules_viewed", "true");
    });
    elements.helpModal.addEventListener("click", (e) => {
        if (e.target === elements.helpModal) toggleHelpModal(false);
    });

    // Game Over Modal buttons
    elements.shareBtn.addEventListener("click", copyShareText);
    elements.modalCloseBtn.addEventListener("click", () => {
        elements.gameOverModal.classList.add("hidden");
    });
    if (elements.resetGameBtn) {
        elements.resetGameBtn.addEventListener("click", () => {
            localStorage.removeItem("wikidle_state");
            window.location.reload();
        });
    }
}

/**
 * Shows/hides the Help Overlay.
 */
function toggleHelpModal(show) {
    if (show) {
        elements.helpModal.classList.remove("hidden");
    } else {
        elements.helpModal.classList.add("hidden");
    }
}

// Start the Game Loop on page load
window.addEventListener("DOMContentLoaded", initGame);
