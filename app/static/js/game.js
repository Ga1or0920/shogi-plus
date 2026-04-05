// ===== 将棋＋ フロントエンド =====

// ─── 定数 ───
const PROMOTED_NAME = { "歩":"と","香":"杏","桂":"圭","銀":"全","角":"馬","飛":"龍" };
const PROMOTABLE = new Set(["歩","香","桂","銀","角","飛"]);
const PROMO_ZONE = { sente: new Set([0,1,2]), gote: new Set([6,7,8]) };

// ─── アプリ状態 ───
let playerName   = "";      // タイトル画面で入力した名前
let gameMode     = null;    // "local" | "cpu" | "online"
let mySide       = null;    // "sente" | "gote" | null（ローカルは両方）
let roomId       = null;
let matchMode    = null;    // "cpu" | "normal" | "rank" | "pvp" — game_start の d.mode
let myRp         = parseInt(localStorage.getItem("shogi_rp") ?? "1000", 10);
let opponentName = null;    // ランクマッチでの相手名

// ─── フェーズ状態 ───
let mulliganSelected  = new Set();  // マリガンで引き直すカードの番号
let placementCardIdx  = null;       // 配置フェーズで選択中のカード番号
let prevTurnPlayer    = null;       // 直前のターンプレイヤー（ターン通知用）
let mulliganDelayed   = false;      // true の間はマリガン表示を保留
let mulliganDelayTimer = null;      // 保留解除タイマー

// ─── 盤面状態 ───
let gameState    = null;
let boardMode    = null;   // {type:"board", from:{row,col}} | {type:"drop", piece} | null
let validTargets = [];

const socket = io();

// ════════════════════════════════════════
//  初期化
// ════════════════════════════════════════
function init() {
  initTitle();
  initSocketEvents();    // 最優先で登録（後続の失敗に左右されないよう先に実行）
  try { initLobby(); } catch (e) { console.error("initLobby error:", e); }
  initGameOverModal();
  initMulliganOverlay();
  showScreen("title");
}

// ════════════════════════════════════════
//  画面切り替え
// ════════════════════════════════════════
function showScreen(name) {
  document.querySelectorAll("main section").forEach(s => s.classList.add("hidden"));
  document.getElementById(`screen-${name}`)?.classList.remove("hidden");

  // タイトル画面ではヘッダーを非表示
  document.querySelector("header").classList.toggle("hidden", name === "title");
  // タイトル・ゲーム画面ではタイトルh1を非表示（ロビー等では表示）
  const h1 = document.querySelector("header h1");
  if (h1) h1.classList.toggle("hidden", name === "title" || name === "game");
  // 「ロビーへ戻る」はゲーム画面のみ表示
  document.getElementById("btn-back").classList.toggle("hidden", name !== "game");
}

// ════════════════════════════════════════
//  タイトル画面
// ════════════════════════════════════════
function initTitle() {
  const input         = document.getElementById("name-input");
  const btnStart      = document.getElementById("btn-start");
  const btnSettingsOpen = document.getElementById("btn-settings-open");
  const btnSettingsBack = document.getElementById("btn-settings-back");

  // 保存済み名前を自動読み込み
  const savedName = localStorage.getItem("shogi_name");
  if (savedName) input.value = savedName;

  const doStart = () => {
    const name = input.value.trim();
    if (!name) {
      input.classList.add("input-error");
      input.focus();
      // アニメーション終了後にクラスを除去
      input.addEventListener("animationend", () => input.classList.remove("input-error"), { once: true });
      return;
    }
    playerName = name;
    localStorage.setItem("shogi_name", name);
    showScreen("lobby");
  };

  btnStart.addEventListener("click", doStart);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doStart(); });

  btnSettingsOpen.addEventListener("click", () => showScreen("settings"));
  btnSettingsBack.addEventListener("click", () => showScreen("title"));
}

// ════════════════════════════════════════
//  ロビー
// ════════════════════════════════════════
function initLobby() {
  document.getElementById("btn-normal").addEventListener("click",  startNormalMatch);
  document.getElementById("btn-rank").addEventListener("click",    startRankMatch);
  document.getElementById("btn-cpu").addEventListener("click",     startCpuGame);
  document.getElementById("btn-room").addEventListener("click",    () => showScreen("room"));
  document.getElementById("btn-normal-back").addEventListener("click", onCancelNormal);
  document.getElementById("btn-cancel-normal").addEventListener("click", onCancelNormal);
  document.getElementById("btn-rank-back").addEventListener("click",   onCancelRank);
  document.getElementById("btn-cancel-rank").addEventListener("click", onCancelRank);
  document.getElementById("btn-room-back").addEventListener("click",   onRoomBack);
  document.getElementById("btn-create-room").addEventListener("click", onCreateRoom);
  document.getElementById("btn-join-room").addEventListener("click",   onJoinRoom);
  document.getElementById("btn-cancel-wait").addEventListener("click", onCancelWait);
  document.getElementById("btn-back").addEventListener("click",        onBack);
  document.getElementById("btn-phase-confirm")?.addEventListener("click", onPhaseConfirm);
}

function resetRoomScreen() {
  document.getElementById("room-actions").classList.remove("hidden");
  document.getElementById("waiting-panel").classList.add("hidden");
  document.getElementById("room-id-input").value = "";
}
function onRoomBack() { resetRoomScreen(); gameMode = null; mySide = null; showScreen("lobby"); }
function startNormalMatch() { gameMode = "online"; mySide = null; showScreen("normal"); socket.emit("join_normal_queue"); }
function onCancelNormal() { socket.emit("cancel_normal_queue"); gameMode = null; mySide = null; showScreen("lobby"); }
function startRankMatch() {
  gameMode = "online"; mySide = null;
  document.getElementById("my-rp-display").textContent = myRp;
  showScreen("rank");
  socket.emit("join_rank_queue", { name: playerName, rp: myRp });
}
function onCancelRank() { socket.emit("cancel_rank_queue"); gameMode = null; mySide = null; showScreen("lobby"); }
function startCpuGame() { gameMode = "cpu"; mySide = "sente"; socket.emit("start_cpu_game"); }
function onCreateRoom() { gameMode = "online"; mySide = "sente"; socket.emit("create_room"); }
function onJoinRoom() {
  const rid = document.getElementById("room-id-input").value.trim().toUpperCase();
  if (rid.length !== 6) { alert("ルームIDは6文字で入力してください"); return; }
  gameMode = "online"; mySide = "gote";
  socket.emit("join_room", { room_id: rid });
}
function onCancelWait() { resetRoomScreen(); gameMode = null; mySide = null; }
function onBack() {
  clearBoardMode(); gameMode = null; mySide = null; roomId = null;
  matchMode = null; opponentName = null;
  clearTimeout(mulliganDelayTimer); mulliganDelayed = false;
  resetRoomScreen(); closeAllModals(); showScreen("lobby");
}
function onReset() {
  if (!confirm("最初からやり直しますか？")) return;
  closeAllModals();
  mulliganSelected.clear(); placementCardIdx = null;
  if      (gameMode === "local")  resetLocalGame();
  else if (gameMode === "cpu")    socket.emit("reset_game");
  else                            socket.emit("reset_game");
}

async function resetLocalGame() {
  const state = await postJSON("/api/reset", {});
  if (state.error) return;
  gameState = state; clearBoardMode(); renderAll();
}

function resetLobbyUI() {
  resetRoomScreen();
}

function showGameScreen(modeLabel) {
  document.getElementById("game-mode-label").textContent = modeLabel;
  const ridLabel = document.getElementById("room-id-label");
  ridLabel.textContent = roomId ? `ルームID: ${roomId}` : "";
  ridLabel.classList.toggle("hidden", !roomId);

  const myLabel  = playerName || "あなた";
  const oppLabel = gameMode === "cpu" ? "CPU"
                 : gameMode === "online" ? (opponentName ?? "相手")
                 : null;

  if (mySide) {
    document.getElementById(`${mySide}-area`).classList.add("my-side");
    const myPrefix = mySide === "sente" ? "先手" : "後手";
    document.getElementById(`${mySide}-name`).textContent = `${myPrefix}（${myLabel}）`;

    const opp       = mySide === "sente" ? "gote" : "sente";
    const oppPrefix = opp === "sente" ? "先手" : "後手";
    document.getElementById(`${opp}-name`).textContent =
      oppLabel ? `${oppPrefix}（${oppLabel}）` : oppPrefix;
  } else {
    // ローカル対戦：名前を先手に表示
    document.getElementById("sente-name").textContent =
      playerName ? `先手（${playerName}）` : "先手";
    document.getElementById("gote-name").textContent = "後手";
  }

  clearBoardMode(); renderAll(); showScreen("game");
}

// ════════════════════════════════════════
//  Socket.IO
// ════════════════════════════════════════
function initSocketEvents() {
  socket.on("connected", (d) => console.log(d.message));

  socket.on("room_created", (d) => {
    roomId = d.room_id;
    document.getElementById("room-id-display").textContent = roomId;
    document.getElementById("room-actions").classList.add("hidden");
    document.getElementById("waiting-panel").classList.remove("hidden");
  });

  socket.on("game_start", (d) => {
    gameState = d.state; mySide = d.your_side; roomId = d.room_id ?? roomId;
    gameMode  = d.mode === "cpu" ? "cpu" : "online";
    matchMode = d.mode;
    opponentName = d.opponent_name ?? null;
    mulliganSelected.clear(); placementCardIdx = null;
    prevTurnPlayer = null;
    // 「対戦開始」を表示してからマリガンを出す
    clearTimeout(mulliganDelayTimer);
    mulliganDelayed = true;
    const modeLabel = d.mode === "cpu" ? "CPU対戦"
                    : d.mode === "rank"   ? "ランクマッチ"
                    : d.mode === "normal" ? "ノーマルマッチ"
                    : "オンライン対戦";
    showGameScreen(modeLabel);
    showNotice(["対戦開始"], 2000);
    mulliganDelayTimer = setTimeout(() => {
      mulliganDelayed = false;
      renderMulliganOverlay();
    }, 2000);
  });

  socket.on("board_update", (d) => {
    const prevPhase  = gameState?.phase;
    const wasMyTurn  = prevTurnPlayer === mySide;
    prevTurnPlayer   = d.state.currentPlayer;
    gameState = d.state;
    if (prevPhase === "mulligan"   && d.state.phase === "placement") mulliganSelected.clear();
    if (prevPhase === "placement"  && d.state.phase === "game")      placementCardIdx = null;
    clearBoardMode(); renderAll();
    handlePostMove();
    // ターン開始通知（ゲームフェーズ中、自分のターンになった瞬間のみ）
    if (d.state.phase === "game" && mySide && !d.state.gameOver
        && d.state.currentPlayer === mySide && !wasMyTurn) {
      showNotice(["あなたのターン", "カードを引きました"], 2000);
    }
  });

  socket.on("normal_waiting", () => { /* マッチング待機中 — UIは既に表示済み */ });
  socket.on("rank_waiting",   () => { /* マッチング待機中 — UIは既に表示済み */ });

  socket.on("rank_result", (d) => {
    myRp = Math.max(0, myRp + d.delta);
    localStorage.setItem("shogi_rp", myRp);
    const rpEl = document.getElementById("gameover-rp");
    if (rpEl) {
      rpEl.textContent = d.delta >= 0 ? `+${d.delta} RP` : `${d.delta} RP`;
      rpEl.className   = `gameover-rp ${d.delta >= 0 ? "rp-gain" : "rp-loss"}`;
      rpEl.classList.remove("hidden");
    }
  });

  socket.on("join_error", (d) => {
    alert(d.message); resetRoomScreen();
  });

  socket.on("opponent_disconnected", () => {
    alert("相手が切断しました。ロビーに戻ります。"); onBack();
  });

  socket.on("moves_result",        () => {});
  socket.on("drop_targets_result", () => {});
  socket.on("error", (d) => console.warn("Server:", d.message));
}

function socketRequest(emitEvent, data, responseEvent) {
  return new Promise((resolve) => {
    socket.once(responseEvent, resolve);
    socket.emit(emitEvent, data);
  });
}

// ════════════════════════════════════════
//  描画
// ════════════════════════════════════════
function renderAll() {
  renderBoard();
  renderCaptured();
  updateTurnIndicator();
  renderKifu();
  updateCpuThinking();
  renderMulliganOverlay();
  renderHandBar();
}


function renderBoard() {
  const boardEl = document.getElementById("shogi-board");
  boardEl.innerHTML = "";

  for (let row = 0; row < 9; row++) {
    for (let col = 0; col < 9; col++) {
      const cell = document.createElement("div");
      cell.classList.add("cell");
      cell.dataset.row = row; cell.dataset.col = col;

      const pd = gameState.board[row][col];
      if (pd) cell.appendChild(createPieceEl(pd));

      // 旗マスの表示
      const flags = gameState.flags;
      if (flags.sente[0] === row && flags.sente[1] === col) cell.classList.add("flag-sente");
      if (flags.gote[0]  === row && flags.gote[1]  === col) cell.classList.add("flag-gote");

      // 配置フェーズ or ゲームフェーズ: カード選択中は配置可能マスをハイライト
      if (mySide && placementCardIdx !== null) {
        const isPlacement = gameState.phase === "placement" && !gameState.placementDone?.[mySide];
        const isGame      = gameState.phase === "game" && canInteract();
        if (isPlacement || isGame) {
          const zone = mySide === "sente" ? [6, 7, 8] : [0, 1, 2];
          const [fr, fc] = flags[mySide];
          if (zone.includes(row) && !pd && !(row === fr && col === fc)) {
            cell.classList.add("placement-target");
          }
        }
      }

      cell.addEventListener("click", () => onCellClick(row, col));
      boardEl.appendChild(cell);
    }
  }

  applyHighlights();
}

function createPieceEl(pd) {
  const el = document.createElement("div");
  el.classList.add("piece");
  if (pd.player === "gote") el.classList.add("gote");
  if (pd.promoted)          el.classList.add("promoted");
  el.textContent = pd.promoted ? (PROMOTED_NAME[pd.piece] ?? pd.piece) : pd.piece;
  return el;
}

function renderCaptured() {
  renderCapturedFor("sente", document.getElementById("sente-captured-list"));
  renderCapturedFor("gote",  document.getElementById("gote-captured-list"));
}

function renderCapturedFor(player, listEl) {
  listEl.innerHTML = "";

  // 相手側（online / CPU）は手札枚数をシルエットで表示
  if (mySide && player !== mySide) {
    const count = gameState.handSize?.[player] ?? 0;
    for (let i = 0; i < count; i++) {
      const el = document.createElement("div");
      el.classList.add("piece-silhouette");
      listEl.appendChild(el);
    }
    return;
  }

  // 自分側：持ち駒を表示
  const pieces = gameState.captured[player] ?? [];
  const counts = {};
  for (const p of pieces) counts[p] = (counts[p] ?? 0) + 1;

  const isMyTurn = gameMode === "local"
    ? player === gameState.currentPlayer
    : player === mySide && player === gameState.currentPlayer;

  for (const [piece, count] of Object.entries(counts)) {
    const el = document.createElement("div");
    el.classList.add("captured-piece");
    el.textContent = piece;

    if (count > 1) {
      const badge = document.createElement("span");
      badge.classList.add("count");
      badge.textContent = count;
      el.appendChild(badge);
    }

    if (isMyTurn && !gameState.gameOver) {
      el.addEventListener("click", () => onCapturedClick(player, piece));
    } else {
      el.style.opacity = "0.45"; el.style.cursor = "default";
    }

    if (boardMode?.type === "drop" && boardMode.piece === piece && isMyTurn) {
      el.classList.add("selected-captured");
    }
    listEl.appendChild(el);
  }
}

function updateTurnIndicator() {
  document.getElementById("sente-area").classList.toggle("active", gameState.currentPlayer === "sente");
  document.getElementById("gote-area").classList.toggle("active",  gameState.currentPlayer === "gote");
}

// ─── 棋譜レンダリング ───
function renderKifu() {
  const listEl = document.getElementById("kifu-list");
  const kifu   = gameState.kifu ?? [];
  listEl.innerHTML = "";

  for (const record of kifu) {
    const entry = document.createElement("div");
    entry.classList.add("kifu-entry", record.player);

    const num = document.createElement("span");
    num.classList.add("kifu-num");
    num.textContent = `${record.num}.`;

    const notation = document.createElement("span");
    notation.classList.add("kifu-notation");
    notation.textContent = record.notation;

    entry.appendChild(num);
    entry.appendChild(notation);
    listEl.appendChild(entry);
  }

  // 最新手へ自動スクロール
  listEl.scrollTop = listEl.scrollHeight;
}

// ─── CPU思考中インジケーター ───
function updateCpuThinking() {
  const el = document.getElementById("cpu-thinking");
  if (gameMode === "cpu" && gameState.currentPlayer === "gote" && !gameState.gameOver) {
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}


function applyHighlights() {
  for (const { row, col } of validTargets) {
    getCellEl(row, col)?.classList.add("movable");
  }
  if (boardMode?.type === "board") {
    getCellEl(boardMode.from.row, boardMode.from.col)?.classList.add("selected");
  }
}

// ════════════════════════════════════════
//  マリガンオーバーレイ
// ════════════════════════════════════════
function initMulliganOverlay() {
  document.getElementById("btn-mulligan-confirm")?.addEventListener("click", onMulliganConfirm);
}

function renderMulliganOverlay() {
  const overlay = document.getElementById("mulligan-overlay");
  if (!overlay) return;

  if (gameState?.phase !== "mulligan" || mulliganDelayed) {
    overlay.classList.remove("visible");
    return;
  }

  overlay.classList.add("visible");
  const done = gameState.mulliganDone?.[mySide];
  const btn  = document.getElementById("btn-mulligan-confirm");
  const wait = document.getElementById("mulligan-waiting");

  if (done) {
    document.getElementById("mulligan-cards").innerHTML = "";
    btn.disabled = true;
    wait?.classList.remove("hidden");
  } else {
    wait?.classList.add("hidden");
    btn.disabled = false;
    renderMulliganCards();
  }
}

function renderMulliganCards() {
  const container = document.getElementById("mulligan-cards");
  const hand = gameState.hand?.[mySide] ?? [];
  container.innerHTML = "";

  hand.forEach((card, i) => {
    const wrapper = document.createElement("div");
    wrapper.classList.add("mulligan-card-wrapper");

    const el = document.createElement("div");
    el.classList.add("mulligan-card");
    el.textContent = card.piece;
    el.classList.toggle("selected", mulliganSelected.has(i));
    wrapper.appendChild(el);

    // バッジは常にDOMに存在させてラッパーの高さを固定（非選択時は不可視）
    const badge = document.createElement("div");
    badge.classList.add("mulligan-redraw-badge");
    badge.textContent = "引き直し";
    badge.style.visibility = mulliganSelected.has(i) ? "visible" : "hidden";
    wrapper.appendChild(badge);

    wrapper.addEventListener("click", () => {
      if (mulliganSelected.has(i)) mulliganSelected.delete(i);
      else mulliganSelected.add(i);
      renderMulliganCards();
    });
    container.appendChild(wrapper);
  });
}

function onMulliganConfirm() {
  if (!gameState || gameState.phase !== "mulligan" || gameState.mulliganDone?.[mySide]) return;
  socket.emit("mulligan", { indices: [...mulliganSelected] });
  mulliganSelected.clear();
  // 確定済み表示
  document.querySelectorAll("#mulligan-cards .mulligan-card-wrapper").forEach(w => {
    w.querySelector(".mulligan-card")?.classList.add("confirmed");
    const b = w.querySelector(".mulligan-redraw-badge"); if (b) b.remove();
  });
  document.getElementById("btn-mulligan-confirm").disabled = true;
}

// ════════════════════════════════════════
//  手札バー（配置フェーズ）
// ════════════════════════════════════════
function renderHandBar() {
  const phase   = gameState?.phase;
  const handBar = document.getElementById("hand-bar");
  if (!handBar) return;
  const title   = document.getElementById("hand-bar-title");
  const btn     = document.getElementById("btn-phase-confirm");

  if (phase === "placement") {
    handBar.classList.remove("hidden");
    btn.classList.remove("hidden");
    const done = gameState.placementDone?.[mySide];
    if (done) {
      title.textContent = "配置確定済み（相手を待っています）";
    } else {
      title.textContent = placementCardIdx !== null
        ? "配置する駒を選択中（盤上のハイライトマスをクリックして配置）"
        : "駒を選んで自陣（下3行）に配置し、確定してください";
    }
    btn.textContent = "配置を確定する";
    btn.disabled    = !!done;
    renderHandCards("placement");

  } else if (phase === "game") {
    handBar.classList.remove("hidden");
    btn.classList.add("hidden");
    title.textContent = placementCardIdx !== null
      ? "配置する駒を選択中（自陣のハイライトマスをクリックして配置）"
      : "手　札";
    renderHandCards("game");

  } else {
    handBar.classList.add("hidden");
  }
}

function renderHandCards(phaseType) {
  const hand  = gameState.hand?.[mySide] ?? [];
  const done  = phaseType === "mulligan"
    ? gameState.mulliganDone?.[mySide]
    : phaseType === "placement"
      ? gameState.placementDone?.[mySide]
      : false;
  const cards = document.getElementById("hand-cards");
  cards.innerHTML = "";

  hand.forEach((card, i) => {
    const el = document.createElement("div");
    el.classList.add("hand-card");
    el.textContent = card.piece;

    if (done) {
      el.classList.add("dimmed");
    } else if (phaseType === "mulligan" && mulliganSelected.has(i)) {
      el.classList.add("selected");
      el.addEventListener("click", () => { mulliganSelected.delete(i); renderHandBar(); });
    } else if ((phaseType === "placement" || phaseType === "game") && placementCardIdx === i) {
      el.classList.add("selected");
      el.addEventListener("click", () => { placementCardIdx = null; renderHandBar(); renderBoard(); });
    } else if (phaseType === "game") {
      const canPlace = canInteract()
        && (gameState.turnPlacements ?? 0) < (gameState.maxPlacementsPerTurn ?? 1);
      if (canPlace) {
        el.addEventListener("click", () => { placementCardIdx = i; renderHandBar(); renderBoard(); });
      } else {
        el.classList.add("dimmed");
      }
    } else {
      el.addEventListener("click", () => {
        if (phaseType === "mulligan") {
          mulliganSelected.add(i);
        } else {
          placementCardIdx = i;
          renderBoard();
        }
        renderHandBar();
      });
    }
    cards.appendChild(el);
  });
}

function onPhaseConfirm() {
  if (!gameState) return;
  if (gameState.phase === "placement" && !gameState.placementDone?.[mySide]) {
    placementCardIdx = null;
    socket.emit("end_placement");
  }
}

// ════════════════════════════════════════
//  インタラクション
// ════════════════════════════════════════
function canInteract() {
  if (!gameState || gameState.gameOver) return false;
  if (gameMode === "cpu"    && gameState.currentPlayer !== "sente") return false;
  if (gameMode === "online" && gameState.currentPlayer !== mySide)  return false;
  return true;
}

async function onCellClick(row, col) {
  if (gameState?.phase === "placement") { await onPlacementClick(row, col); return; }
  if (gameState?.phase === "mulligan")  return;
  if (!canInteract()) return;
  const pd = gameState.board[row][col];

  // ゲームフェーズ中にカード選択済み → 自陣への配置を試みる
  if (gameState.phase === "game" && placementCardIdx !== null) {
    const zone = mySide === "sente" ? [6, 7, 8] : [0, 1, 2];
    const [fr, fc] = gameState.flags[mySide];
    if (pd === null && zone.includes(row) && !(row === fr && col === fc)) {
      socket.emit("play_card", { card_index: placementCardIdx, row, col });
      socket.emit("end_turn");
    }
    placementCardIdx = null;
    renderHandBar();
    renderBoard();
    return;
  }

  // ① 有効な移動先をクリック → 実行
  if (boardMode && validTargets.some(t => t.row === row && t.col === col)) {
    await executeTarget(row, col); return;
  }

  // ② 自分の駒をクリック → 選択
  if (pd && pd.player === gameState.currentPlayer) {
    clearBoardMode();
    const data = await getMoves(row, col);
    validTargets = data.moves;
    boardMode = { type: "board", from: { row, col } };
    renderBoard(); renderCaptured(); return;
  }

  // ③ キャンセル
  if (boardMode) { clearBoardMode(); renderBoard(); renderCaptured(); }
}

async function onPlacementClick(row, col) {
  if (!mySide || gameState.placementDone?.[mySide]) return;
  const zone = mySide === "sente" ? [6, 7, 8] : [0, 1, 2];
  const pd   = gameState.board[row][col];
  const [fr, fc] = gameState.flags[mySide];

  // 自分の配置済み駒をクリック → 手札に戻す
  if (pd && pd.player === mySide && zone.includes(row)) {
    socket.emit("unplace_piece", { row, col });
    placementCardIdx = null;
    return;
  }

  // カード選択中 → 空きマスに配置
  if (placementCardIdx !== null && pd === null
      && zone.includes(row) && !(row === fr && col === fc)) {
    socket.emit("place_piece", { card_index: placementCardIdx, row, col });
    placementCardIdx = null;
    return;
  }

  // その他（選択解除）
  if (placementCardIdx !== null) {
    placementCardIdx = null;
    renderHandBar();
    renderBoard();
  }
}

async function onCapturedClick(player, piece) {
  if (!canInteract()) return;
  clearBoardMode();
  const data = await getDropTargets(piece);
  validTargets = data.targets;
  boardMode = { type: "drop", piece };
  renderBoard(); renderCaptured();
}

// ─── 移動・打ち実行 ───
async function executeTarget(toRow, toCol) {
  if (boardMode.type === "board") {
    const { row: fr, col: fc } = boardMode.from;
    await executeBoardMove(fr, fc, toRow, toCol);
  } else {
    await executeDrop(boardMode.piece, toRow, toCol);
  }
}

async function executeBoardMove(fr, fc, tr, tc) {
  const pd = gameState.board[fr][fc];
  const { piece, player, promoted } = pd;

  if (!promoted && PROMOTABLE.has(piece)) {
    if (mustPromote(piece, player, tr)) { await doMove(fr,fc,tr,tc,true);  return; }
    if (canPromote(player, fr, tr))     {
      showPromotionModal(piece, (promote) => doMove(fr,fc,tr,tc,promote));
      return;
    }
  }
  await doMove(fr, fc, tr, tc, false);
}

async function doMove(fr, fc, tr, tc, promote) {
  clearBoardMode();
  if (gameMode === "local") {
    const state = await postJSON("/api/move",
      { from_row: fr, from_col: fc, to_row: tr, to_col: tc, promote });
    if (state.error) return;
    gameState = state; renderAll(); handlePostMove();
    socket.emit("end_turn");
  } else {
    socket.emit("make_move",
      { from_row: fr, from_col: fc, to_row: tr, to_col: tc, promote });
    socket.emit("end_turn");
  }
}

async function executeDrop(piece, row, col) {
  clearBoardMode();
  if (gameMode === "local") {
    const state = await postJSON("/api/drop", { piece, row, col });
    if (state.error) return;
    gameState = state; renderAll(); handlePostMove();
    socket.emit("end_turn");
  } else {
    socket.emit("make_drop", { piece, row, col });
    socket.emit("end_turn");
  }
}

// ─── 手の後処理（王手・詰み） ───
function handlePostMove() {
  if (gameState.gameOver) {
    showGameOverModal();
  }
  // check の表示は renderAll() 内で処理済み
}

// ─── 合法手・打ち先の取得 ───
async function getMoves(row, col) {
  if (gameMode === "local") return fetchJSON(`/api/moves?row=${row}&col=${col}`);
  return socketRequest("request_moves", { row, col }, "moves_result");
}
async function getDropTargets(piece) {
  if (gameMode === "local") return fetchJSON(`/api/drop-targets?piece=${encodeURIComponent(piece)}`);
  return socketRequest("request_drop_targets", { piece }, "drop_targets_result");
}

// ════════════════════════════════════════
//  成り
// ════════════════════════════════════════
function canPromote(player, fromRow, toRow) {
  return PROMO_ZONE[player].has(fromRow) || PROMO_ZONE[player].has(toRow);
}
function mustPromote(piece, player, toRow) {
  if (player === "sente") {
    if ((piece==="歩"||piece==="香") && toRow===0) return true;
    if (piece==="桂" && toRow<=1) return true;
  } else {
    if ((piece==="歩"||piece==="香") && toRow===8) return true;
    if (piece==="桂" && toRow>=7) return true;
  }
  return false;
}

function showPromotionModal(piece, callback) {
  document.getElementById("modal-promoted-piece").textContent = PROMOTED_NAME[piece] ?? piece;
  document.getElementById("modal-original-piece").textContent = piece;

  const modal       = document.getElementById("promotion-modal");
  const btnPromote  = document.getElementById("btn-promote");
  const btnNoPromote= document.getElementById("btn-no-promote");
  modal.classList.add("visible");

  const close = (promote) => {
    modal.classList.remove("visible");
    btnPromote.onclick = null; btnNoPromote.onclick = null;
    callback(promote);
  };
  btnPromote.onclick   = () => close(true);
  btnNoPromote.onclick = () => close(false);
}

// ════════════════════════════════════════
//  ゲーム終了モーダル
// ════════════════════════════════════════
function initGameOverModal() {
  document.getElementById("btn-gameover-restart").addEventListener("click", () => {
    closeAllModals(); onReset();
  });
  document.getElementById("btn-gameover-close").addEventListener("click", () => {
    closeAllModals();
  });
}

function showGameOverModal() {
  const winner = gameState.winner;
  const winnerLabel = winner === "sente" ? "先手" : "後手";

  // CPU/online では「あなた」「相手」で表示
  let displayLabel = winnerLabel;
  if (mySide) {
    displayLabel = winner === mySide ? "あなた" : (gameMode === "cpu" ? "CPU" : "相手");
  }

  document.getElementById("gameover-winner").textContent = `${displayLabel}の勝ち`;
  document.getElementById("gameover-label").textContent  = "旗に到達！";
  // RP表示はrank_resultイベント受信時に更新する
  document.getElementById("gameover-rp").classList.add("hidden");

  document.getElementById("gameover-modal").classList.add("visible");
}

function closeAllModals() {
  document.querySelectorAll(".modal-overlay").forEach(m => m.classList.remove("visible"));
}

// ════════════════════════════════════════
//  ユーティリティ
// ════════════════════════════════════════
function clearBoardMode() { boardMode = null; validTargets = []; }

// ─── 中央通知 ───
function showNotice(lines, duration = 2000) {
  const el = document.getElementById("game-notice");
  if (!el) return;
  const box = el.querySelector(".game-notice-box");
  box.innerHTML = "";
  lines.forEach((line, i) => {
    const div = document.createElement("div");
    div.classList.add(i === 0 ? "game-notice-main" : "game-notice-sub");
    div.textContent = line;
    box.appendChild(div);
  });
  el.classList.add("visible");
  clearTimeout(el._noticeTimer);
  el._noticeTimer = setTimeout(() => el.classList.remove("visible"), duration);
}

function getCellEl(row, col) {
  return document.querySelector(`.cell[data-row="${row}"][data-col="${col}"]`);
}

async function fetchJSON(url)       { return (await fetch(url)).json(); }
async function postJSON(url, body)  {
  return (await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })).json();
}

// ════════════════════════════════════════
//  起動
// ════════════════════════════════════════
init();
