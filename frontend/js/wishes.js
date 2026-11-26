/** Wish wall: anonymous submissions with SVG CAPTCHA and admin moderation. */

let _wishCaptchaId = null;
let _wishLoaded = false;
const WISH_ADMIN_KEY = "wishAdminToken";

function _wishEl(id) { return document.getElementById(id); }

function _getAdminToken() {
    return sessionStorage.getItem(WISH_ADMIN_KEY) || "";
}

function _showWishMsg(text, isError, el = _wishEl("wishMsg")) {
    el.textContent = text;
    el.className = "wish-msg " + (isError ? "is-error" : "is-ok");
}

function _updateWishCount() {
    const input = _wishEl("wishText");
    _wishEl("wishCount").textContent = `${input.value.length} / ${input.maxLength}`;
}

function openWishDialog() {
    const dialog = _wishEl("wishComposeDialog");
    if (!dialog) return;
    const msg = _wishEl("wishMsg");
    if (msg) msg.textContent = "";
    if (!_wishCaptchaId) loadCaptcha();
    if (!dialog.open) {
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");
    }
    const input = _wishEl("wishText");
    if (input) input.focus();
}

function closeWishDialog() {
    const dialog = _wishEl("wishComposeDialog");
    if (!dialog || !dialog.open) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
}

function ensureWishesLoaded() {
    if (_wishLoaded) return;
    _wishLoaded = true;
    loadWishes();
}

// SVG comes from our own backend; injecting it as markup is safe and required
// to render the image. User-supplied content is never injected this way.
function loadCaptcha() {
    const box = _wishEl("wishCaptchaBox");
    _wishCaptchaId = null;
    _wishEl("wishCaptchaInput").value = "";
    box.disabled = true;
    box.textContent = "…";
    fetch(WISH_CAPTCHA_ENDPOINT)
        .then(r => {
            if (!r.ok) throw new Error();
            return r.json();
        })
        .then(d => {
            _wishCaptchaId = d.captcha_id;
            box.innerHTML = d.svg;
        })
        .catch(() => { box.textContent = "↻"; })
        .finally(() => { box.disabled = false; });
}

function _appendWishTime(container, ts) {
    if (!ts) return;
    const date = new Date(ts * 1000);
    if (!Number.isFinite(date.getTime())) return;
    const pad = n => String(n).padStart(2, "0");
    const time = document.createElement("time");
    time.dateTime = date.toISOString();
    time.textContent = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    container.appendChild(time);
}

function _renderWishCard(wish) {
    const card = document.createElement("article");
    card.className = "wish-card";

    const meta = document.createElement("header");
    meta.className = "wish-card-meta";

    const nick = document.createElement("span");
    nick.className = "wish-card-nick";
    nick.textContent = wish.nick || __("wishes.anonymous");
    meta.appendChild(nick);
    _appendWishTime(meta, wish.ts);
    card.appendChild(meta);

    const text = document.createElement("p");
    text.className = "wish-card-text";
    text.textContent = wish.text || "";
    card.appendChild(text);

    if (wish.reply) {
        const reply = document.createElement("div");
        reply.className = "wish-card-reply";

        const head = document.createElement("div");
        head.className = "wish-card-reply-head";
        const label = document.createElement("span");
        label.className = "wish-card-reply-label";
        label.textContent = __("wishes.adminReply");
        head.appendChild(label);
        _appendWishTime(head, wish.reply_ts);

        const replyText = document.createElement("p");
        replyText.className = "wish-card-reply-text";
        replyText.textContent = wish.reply;
        reply.append(head, replyText);
        card.appendChild(reply);
    }

    if (_getAdminToken()) {
        const details = document.createElement("details");
        details.className = "wish-admin";
        const summary = document.createElement("summary");
        summary.textContent = __("wishes.manage");
        details.appendChild(summary);

        const form = document.createElement("form");
        form.className = "wish-reply-form";
        const input = document.createElement("textarea");
        input.rows = 4;
        input.maxLength = 200;
        input.placeholder = __("wishes.replyPlaceholder");
        input.setAttribute("aria-label", __("wishes.adminReply"));
        input.value = wish.reply || "";

        const actions = document.createElement("div");
        actions.className = "wish-reply-actions";
        const save = document.createElement("button");
        save.type = "submit";
        save.className = "pc-btn";
        save.textContent = wish.reply ? __("wishes.updateReply") : __("wishes.reply");
        const del = document.createElement("button");
        del.type = "button";
        del.className = "pc-btn wish-card-del";
        del.textContent = __("wishes.delete");
        actions.append(save, del);

        const status = document.createElement("div");
        status.className = "wish-msg";
        status.setAttribute("role", "status");
        form.append(input, actions, status);
        input.addEventListener("input", () => { status.textContent = ""; });
        form.addEventListener("submit", event => {
            event.preventDefault();
            replyWish(wish.id, input.value, save, status);
        });
        del.addEventListener("click", () => deleteWish(wish.id, del, status));
        details.appendChild(form);
        card.appendChild(details);
    }

    return card;
}

function loadWishes() {
    const loading = _wishEl("wishLoading");
    const empty = _wishEl("wishEmpty");
    const list = _wishEl("wishList");
    const feedMsg = _wishEl("wishFeedMsg");
    loading.hidden = list.childElementCount > 0;
    empty.hidden = true;
    fetch(WISHES_ENDPOINT)
        .then(r => {
            if (!r.ok) throw new Error();
            return r.json();
        })
        .then(d => {
            const wishes = d.wishes || [];
            list.replaceChildren(...wishes.map(_renderWishCard));
            empty.hidden = wishes.length > 0;
            if (feedMsg.classList.contains("is-error")) feedMsg.textContent = "";
        })
        .catch(() => _showWishMsg(__("wishes.loadFailed"), true, feedMsg))
        .finally(() => { loading.hidden = true; });
}

function submitWish() {
    _wishEl("wishMsg").textContent = "";
    const text = _wishEl("wishText").value.trim();
    const nick = _wishEl("wishNick").value.trim();
    const answer = _wishEl("wishCaptchaInput").value.trim();
    if (!text) { _showWishMsg(__("wishes.errorEmpty"), true); return; }
    if (!answer || !_wishCaptchaId) { _showWishMsg(__("wishes.errorCaptcha"), true); return; }

    const btn = _wishEl("wishSubmitBtn");
    btn.disabled = true;
    fetch(WISHES_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            text: text,
            nick: nick,
            captcha_id: _wishCaptchaId,
            captcha_answer: answer,
        }),
    })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || __("wishes.errorSubmit"));
            return data;
        })
        .then(() => {
            _wishEl("wishText").value = "";
            _wishEl("wishCaptchaInput").value = "";
            _wishCaptchaId = null;
            _updateWishCount();
            closeWishDialog();
            _showWishMsg(__("wishes.success"), false, _wishEl("wishFeedMsg"));
            loadWishes();
        })
        .catch(err => {
            _showWishMsg(err.message || __("wishes.errorSubmit"), true);
            loadCaptcha();  // captcha is one-time; always refresh after a try
        })
        .finally(() => { btn.disabled = false; });
}

function replyWish(wishId, text, btn, status) {
    const reply = (text || "").trim();
    if (!reply) { _showWishMsg(__("wishes.errorReplyEmpty"), true, status); return; }
    btn.disabled = true;
    fetch(`${WISHES_ENDPOINT}/${encodeURIComponent(wishId)}/reply`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
            "X-Admin-Token": _getAdminToken(),
        },
        body: JSON.stringify({ reply }),
    })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || __("wishes.errorReply"));
            return data;
        })
        .then(() => {
            _showWishMsg(__("wishes.replySuccess"), false, _wishEl("wishFeedMsg"));
            loadWishes();
        })
        .catch(err => _showWishMsg(err.message || __("wishes.errorReply"), true, status))
        .finally(() => { btn.disabled = false; });
}

function deleteWish(wishId, btn, status) {
    btn.disabled = true;
    fetch(`${WISHES_ENDPOINT}/${encodeURIComponent(wishId)}`, {
        method: "DELETE",
        headers: { "X-Admin-Token": _getAdminToken() },
    })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || __("wishes.errorDelete"));
            return data;
        })
        .then(() => loadWishes())
        .catch(err => _showWishMsg(err.message || __("wishes.errorDelete"), true, status))
        .finally(() => { btn.disabled = false; });
}

function _initWishAdmin() {
    const input = _wishEl("wishAdminToken");
    const hint = _wishEl("wishAdminHint");
    const panel = input.closest(".wish-admin");

    document.addEventListener("click", event => {
        if (!panel.contains(event.target)) panel.open = false;
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && panel.open) {
            panel.open = false;
            panel.querySelector("summary").focus();
        }
    });

    const refreshHint = () => {
        hint.textContent = _getAdminToken() ? __("wishes.adminEnabled") : "";
        _syncVpnPanel();
    };
    input.value = _getAdminToken();
    refreshHint();

    _wishEl("wishAdminSave").addEventListener("click", () => {
        const val = input.value.trim();
        if (!val) {
            sessionStorage.removeItem(WISH_ADMIN_KEY);
            refreshHint();
            loadWishes();
            return;
        }
        // Validate against the server before enabling delete, so a wrong token
        // gives immediate feedback instead of silently "saving".
        const saveBtn = _wishEl("wishAdminSave");
        saveBtn.disabled = true;
        hint.textContent = __("wishes.verifying");
        fetch(WISH_VERIFY_ADMIN_ENDPOINT, {
            method: "POST",
            headers: { "X-Admin-Token": val },
        })
            .then(r => {
                if (!r.ok) throw new Error(__("wishes.invalidToken"));
                sessionStorage.setItem(WISH_ADMIN_KEY, val);
                hint.textContent = __("wishes.adminEnabled");
                _syncVpnPanel();
                loadWishes();  // re-render to show admin actions
            })
            .catch(() => {
                sessionStorage.removeItem(WISH_ADMIN_KEY);
                input.value = "";
                hint.textContent = __("wishes.invalidToken");
                _syncVpnPanel();
                loadWishes();
            })
            .finally(() => { saveBtn.disabled = false; });
    });
}

function _formatVpnBytes(bytes) {
    const n = Number(bytes || 0);
    if (!Number.isFinite(n) || n <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let idx = 0;
    let val = n;
    while (val >= 1024 && idx < units.length - 1) {
        val /= 1024;
        idx += 1;
    }
    return `${val >= 100 || idx === 0 ? val.toFixed(0) : val.toFixed(2)} ${units[idx]}`;
}

function _createVpnCard(label, value, sub) {
    const card = document.createElement("div");
    card.className = "wish-vpn-card";
    const l = document.createElement("div");
    l.className = "wish-vpn-card-label";
    l.textContent = label;
    const v = document.createElement("div");
    v.className = "wish-vpn-card-value";
    v.textContent = value;
    card.append(l, v);
    if (sub) {
        const s = document.createElement("div");
        s.className = "wish-vpn-card-sub";
        s.textContent = sub;
        card.appendChild(s);
    }
    return card;
}

function _renderVpnData(data) {
    const cardsEl = _wishEl("wishVpnCards");
    const tbody = _wishEl("wishVpnNodesBody");
    const badge = _wishEl("wishVpnSummaryBadge");
    const msg = _wishEl("wishVpnStatusMsg");
    if (!cardsEl || !tbody) return;

    if (!data || !data.configured) {
        cardsEl.replaceChildren();
        tbody.replaceChildren();
        if (badge) badge.textContent = "";
        _showWishMsg((data && data.error) || __("wishes.vpnNotConfigured"), true, msg);
        return;
    }

    const group = data.group || {};
    const traffic = data.traffic || {};
    const hit = data.last_hit || null;
    const hitNodeName = hit && hit.node ? hit.node : null;

    if (badge) {
        badge.textContent = `${group.alive_nodes || 0} / ${group.total_nodes || 0} · ${_formatVpnBytes(traffic.total_bytes)}`;
    }

    const hitValue = hitNodeName
        ? `${hitNodeName}`
        : __("wishes.vpnNoHit");
    const hitSubParts = [];
    if (hit) {
        if (hit.status_code != null) hitSubParts.push(`HTTP ${hit.status_code}`);
        if (hit.node_delay_ms != null) hitSubParts.push(`${hit.node_delay_ms} ms`);
        if (hit.latency_ms != null) hitSubParts.push(`RTT ${hit.latency_ms} ms`);
        if (hit.error) hitSubParts.push(hit.error);
    }

    const trafficValue = _formatVpnBytes(traffic.total_bytes);
    const trafficSub = `↑ ${_formatVpnBytes(traffic.upload_bytes)} · ↓ ${_formatVpnBytes(traffic.download_bytes)}`;
    const nodesValue = `${group.alive_nodes || 0} / ${group.total_nodes || 0}`;
    const nodesSub = [group.name, group.type].filter(Boolean).join(" · ");

    cardsEl.replaceChildren(
        _createVpnCard(__("wishes.vpnHitCard"), hitValue, hitSubParts.join(" · ")),
        _createVpnCard(__("wishes.vpnTrafficCard"), trafficValue, trafficSub),
        _createVpnCard(__("wishes.vpnNodesCard"), nodesValue, nodesSub)
    );

    const rows = (data.nodes || []).map(node => {
        const tr = document.createElement("tr");
        if (hitNodeName && node.name === hitNodeName) {
            tr.className = "is-hit";
        }
        const tdName = document.createElement("td");
        tdName.textContent = node.name || "";
        if (hitNodeName && node.name === hitNodeName) {
            const tag = document.createElement("span");
            tag.className = "wish-vpn-badge is-ok";
            tag.style.marginLeft = "6px";
            tag.textContent = __("wishes.vpnHitTag");
            tdName.appendChild(tag);
        }

        const tdType = document.createElement("td");
        tdType.textContent = node.type || "-";

        const tdStatus = document.createElement("td");
        const stBadge = document.createElement("span");
        stBadge.className = `wish-vpn-badge ${node.delay_ms != null ? "is-ok" : "is-down"}`;
        stBadge.textContent = node.delay_ms != null ? __("wishes.vpnOnline") : __("wishes.vpnOffline");
        tdStatus.appendChild(stBadge);

        const tdDelay = document.createElement("td");
        tdDelay.textContent = node.delay_ms != null ? `${node.delay_ms} ms` : "-";

        tr.append(tdName, tdType, tdStatus, tdDelay);
        return tr;
    });
    tbody.replaceChildren(...rows);
}

function _setVpnBusy(busy) {
    ["wishVpnRefreshBtn", "wishVpnProbeBtn", "wishVpnSpeedtestBtn"].forEach(id => {
        const el = _wishEl(id);
        if (el) el.disabled = busy;
    });
}

function loadVpnStatus() {
    const token = _getAdminToken();
    const msg = _wishEl("wishVpnStatusMsg");
    if (!token) return;
    _setVpnBusy(true);
    if (msg) msg.textContent = "";
    fetch(WISH_VPN_STATUS_ENDPOINT, {
        headers: { "X-Admin-Token": token },
    })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || __("wishes.vpnLoadFailed"));
            return data;
        })
        .then(_renderVpnData)
        .catch(err => _showWishMsg(err.message || __("wishes.vpnLoadFailed"), true, msg))
        .finally(() => _setVpnBusy(false));
}

function probeVpn(refreshDelays) {
    const token = _getAdminToken();
    const msg = _wishEl("wishVpnStatusMsg");
    if (!token) return;
    _setVpnBusy(true);
    if (msg) msg.textContent = "";
    fetch(WISH_VPN_PROBE_ENDPOINT, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Admin-Token": token,
        },
        body: JSON.stringify({ refresh_delays: Boolean(refreshDelays) }),
    })
        .then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || __("wishes.vpnLoadFailed"));
            return data;
        })
        .then(_renderVpnData)
        .catch(err => _showWishMsg(err.message || __("wishes.vpnLoadFailed"), true, msg))
        .finally(() => _setVpnBusy(false));
}

function _syncVpnPanel() {
    const panel = _wishEl("wishVpnPanel");
    if (!panel) return;
    const isAdmin = Boolean(_getAdminToken());
    panel.hidden = !isAdmin;
    if (isAdmin && panel.open) {
        loadVpnStatus();
    }
}

function _initWishVpn() {
    const panel = _wishEl("wishVpnPanel");
    if (!panel) return;
    panel.addEventListener("toggle", () => {
        if (panel.open && _getAdminToken()) {
            loadVpnStatus();
        }
    });
    const refreshBtn = _wishEl("wishVpnRefreshBtn");
    const probeBtn = _wishEl("wishVpnProbeBtn");
    const speedBtn = _wishEl("wishVpnSpeedtestBtn");
    if (refreshBtn) refreshBtn.addEventListener("click", loadVpnStatus);
    if (probeBtn) probeBtn.addEventListener("click", () => probeVpn(false));
    if (speedBtn) speedBtn.addEventListener("click", () => probeVpn(true));
    _syncVpnPanel();
}

document.addEventListener("DOMContentLoaded", () => {
    const form = _wishEl("wishForm");
    if (!form) return;

    form.addEventListener("submit", event => {
        event.preventDefault();
        submitWish();
    });
    _wishEl("wishText").addEventListener("input", _updateWishCount);
    _updateWishCount();
    _wishEl("wishCaptchaBox").addEventListener("click", loadCaptcha);

    const openBtn = _wishEl("wishOpenModalBtn");
    if (openBtn) openBtn.addEventListener("click", openWishDialog);

    const closeBtn = _wishEl("wishDialogClose");
    if (closeBtn) closeBtn.addEventListener("click", closeWishDialog);

    const dialog = _wishEl("wishComposeDialog");
    if (dialog) {
        dialog.addEventListener("click", event => {
            if (event.target === dialog) closeWishDialog();
        });
    }

    _initWishAdmin();
    _initWishVpn();

    // Lazy-load on first switch to the 心愿墙 tab or when opened directly at /wishes.
    document.querySelectorAll('.tab-btn[data-tab="wishes"]').forEach(btn => {
        btn.addEventListener("click", ensureWishesLoaded);
    });
    const panel = _wishEl("tab-wishes");
    if (panel && panel.classList.contains("active")) {
        ensureWishesLoaded();
    }
});

