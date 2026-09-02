// FinAgent 量化平台：SPA 路由 + 页面逻辑
const container = document.getElementById("page-container");

// ---------- 认证 ----------
const TOKEN_KEY = "finagent_token";
const USER_KEY = "finagent_user";

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function getUser() { return localStorage.getItem(USER_KEY); }

function setAuth(token, username) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, username);
}

function clearAuth() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

function showAuthPage() {
    document.getElementById("auth-page").style.display = "flex";
    document.getElementById("app-shell").style.display = "none";
}

function showApp() {
    document.getElementById("auth-page").style.display = "none";
    document.getElementById("app-shell").style.display = "block";
    document.getElementById("nav-username").textContent = getUser() || "";
}

function showLogin() {
    document.getElementById("login-form").style.display = "block";
    document.getElementById("register-form").style.display = "none";
}

function showRegister() {
    document.getElementById("login-form").style.display = "none";
    document.getElementById("register-form").style.display = "block";
}

async function doLogin() {
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    if (!username || !password) { alert("请输入用户名和密码"); return; }
    try {
        const resp = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (resp.ok) {
            setAuth(data.access_token, data.username);
            showApp();
            navigate("home");
            showRiskModal();  // 每次登录后弹风险提示
        } else {
            alert(data.detail || "登录失败");
        }
    } catch (e) { alert("登录出错：" + e.message); }
}

async function doRegister() {
    const username = document.getElementById("reg-username").value.trim();
    const password = document.getElementById("reg-password").value;
    if (!username || !password) { alert("请输入用户名和密码"); return; }
    try {
        const resp = await fetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });
        const data = await resp.json();
        if (resp.ok) {
            alert("注册成功，请登录");
            showLogin();
        } else {
            alert(data.detail || "注册失败");
        }
    } catch (e) { alert("注册出错：" + e.message); }
}

function logout() {
    clearAuth();
    showAuthPage();
}

// ---------- 首页聊天（SSE 流式）----------
let homeChatHistory = [];
let currentThreadId = null;

// 生成唯一 thread_id
function genThreadId() {
    return "conv-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
}

// 新建对话
async function newConversation() {
    currentThreadId = genThreadId();
    homeChatHistory = [];
    // 保存会话（服务端）
    await apiFetch("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: currentThreadId }),
    });
    const box = document.getElementById("home-chat-box");
    box.innerHTML = '<div class="chat-msg bot">你好！我是 FinAgent 助手，有什么可以帮你？可以问我股票、行情等金融问题。</div>';
    loadConversations();
}

// 加载会话列表
async function loadConversations() {
    const list = document.getElementById("conv-list");
    try {
        const resp = await apiFetch("/api/conversations");
        const convs = await resp.json();
        list.innerHTML = convs.map(c =>
            `<div class="conv-item ${c.thread_id === currentThreadId ? 'active' : ''}">
                <span class="conv-title" onclick="loadConversation('${c.thread_id}')">${c.title || "新对话"}</span>
                <span class="conv-actions">
                    <button class="conv-btn" onclick="renameConversation('${c.thread_id}','${(c.title||'').replace(/'/g,"\\'")}')">✎</button>
                    <button class="conv-btn" onclick="deleteConversation('${c.thread_id}')">🗑</button>
                </span>
            </div>`
        ).join("") || '<div class="conv-empty">暂无会话</div>';
    } catch (e) { /* 忽略 */ }
}

// 重命名会话
async function renameConversation(threadId, oldTitle) {
    const newTitle = prompt("输入新名称：", oldTitle);
    if (!newTitle || newTitle === oldTitle) return;
    await apiFetch("/api/conversations/rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId, title: newTitle }),
    });
    loadConversations();
}

// 删除会话
async function deleteConversation(threadId) {
    if (!confirm("确定删除该会话？")) return;
    await apiFetch(`/api/conversations/${threadId}`, { method: "DELETE" });
    if (currentThreadId === threadId) {
        currentThreadId = null;
        document.getElementById("home-chat-box").innerHTML =
            '<div class="chat-msg bot">你好！我是 FinAgent 助手，有什么可以帮你？可以问我股票、行情等金融问题。</div>';
    }
    loadConversations();
}

// 隐藏/显示侧栏（按钮在侧栏内，跟着侧栏一起走；收起后由展开条唤起）
function toggleSidebar() {
    document.getElementById("conv-sidebar").classList.toggle("hidden");
}

// 加载指定会话
async function loadConversation(threadId) {
    currentThreadId = threadId;
    const resp = await apiFetch(`/api/conversations/messages?thread_id=${threadId}`);
    const data = await resp.json();
    const box = document.getElementById("home-chat-box");
    box.innerHTML = "";
    homeChatHistory = [];
    (data.messages || []).forEach(m => {
        appendHomeMsg(m.role === "user" ? "user" : "bot", m.content);
        homeChatHistory.push({ role: m.role, content: m.content });
    });
    loadConversations();
}

// 首页聊天初始化：加载会话列表 + 默认打开最近会话
async function initHomeChat() {
    try {
        const resp = await apiFetch("/api/conversations");
        const convs = await resp.json();
        loadConversations();
        if (convs.length > 0 && !currentThreadId) {
            // 默认加载最近一个会话
            currentThreadId = convs[0].thread_id;
            loadConversation(currentThreadId);
        }
    } catch (e) { /* 忽略 */ }
}

// 保存消息到会话
async function saveMsg(role, content) {
    if (!currentThreadId) return;
    try {
        await apiFetch("/api/conversations/messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: currentThreadId, role, content }),
        });
    } catch (e) { /* 忽略 */ }
    loadConversations();
}

async function sendHomeChat() {
    const input = document.getElementById("home-chat-input");
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    const box = document.getElementById("home-chat-box");
    // 没有会话则先新建
    if (!currentThreadId) {
        currentThreadId = genThreadId();
        apiFetch("/api/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: currentThreadId }),
        });
    }
    // 显示用户消息 + 保存
    appendHomeMsg("user", q);
    homeChatHistory.push({ role: "user", content: q });
    saveMsg("user", q);
    // 只保留最近 7 轮
    homeChatHistory = homeChatHistory.slice(-14);
    // 创建机器人消息（打字机流式填充）
    resetTypeWriter();
    const botDiv = appendHomeMsg("bot", "");
    try {
        const resp = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + getToken(),
            },
            body: JSON.stringify({
                question: q,
                thread_id: currentThreadId,
                messages: homeChatHistory,  // 最近7轮上下文
            }),
        });
        // SSE 流式读取
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let full = "";
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            const lines = text.split("\n");
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const data = line.slice(6);
                    if (data === "[DONE]") continue;
                    if (data.startsWith("[ERROR]")) {
                        full = data;
                        resetTypeWriter();
                        botDiv.textContent = full;
                        break;
                    }
                    full += data;
                    typeAppend(botDiv, box, data);  // 打字机逐字渲染（网络缓冲兜底）
                }
            }
        }
        // 无内容 → 移除空机器人消息；话术（超限提示）不存历史
        if (!full.trim()) {
            resetTypeWriter();
            botDiv.remove();
        } else if (full.includes("我是金融助手")) {
            /* 超限话术不存历史 */
        } else {
            homeChatHistory.push({ role: "assistant", content: full });
            saveMsg("assistant", full);
        }
    } catch (e) {
        resetTypeWriter();
        botDiv.textContent = "出错了：" + e.message;
    }
}

// ---------- 打字机流式渲染 ----------
// 后端 SSE 若因网络缓冲一次性到达，这里按字符逐字显示，保证"流式"观感
let typeBuf = [];
let typeTimer = null;

function resetTypeWriter() {
    typeBuf = [];
    if (typeTimer) { clearInterval(typeTimer); typeTimer = null; }
}

function typeAppend(botDiv, box, text) {
    for (const ch of text) typeBuf.push(ch);
    if (typeTimer) return;
    typeTimer = setInterval(() => {
        let batch = "";
        while (batch.length < 6 && typeBuf.length) batch += typeBuf.shift();
        if (batch) {
            botDiv.textContent += batch;
            if (box) box.scrollTop = box.scrollHeight;
        }
        if (!typeBuf.length) { clearInterval(typeTimer); typeTimer = null; }
    }, 25);
}

function appendHomeMsg(role, text) {
    const box = document.getElementById("home-chat-box");
    const div = document.createElement("div");
    div.className = "chat-msg " + role;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

// 推荐策略快捷输入：点击 → 自动填入输入框并发送
function useQuickPrompt(text) {
    const input = document.getElementById("home-chat-input");
    if (input) input.value = text;
    sendHomeChat();
}

// 回车发送
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && document.getElementById("home-chat-input")) {
        sendHomeChat();
    }
});

// ---------- 风险提示弹窗 ----------
function showRiskModal() {
    document.getElementById("risk-modal").style.display = "flex";
}

function closeRiskModal() {
    document.getElementById("risk-modal").style.display = "none";
}

// ---------- 带 token 的请求封装 ----------
async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    const resp = await fetch(url, { ...options, headers });
    if (resp.status === 401) {
        alert("登录已过期，请重新登录");
        clearAuth();
        showAuthPage();
        throw new Error("未授权");
    }
    return resp;
}

// 常用指数基准选项
const BENCHMARKS = [
    { code: "sh000300", name: "沪深300" },
    { code: "sh000001", name: "上证指数" },
    { code: "sh000905", name: "中证500" },
    { code: "sz399001", name: "深证成指" },
    { code: "sz399006", name: "创业板指" },
];

// ---------- 页面模板 ----------
const pages = {
    home: `
        <div class="page" id="page-home">
            <div class="home-layout">
                <!-- 左侧：标题 + 功能入口（无框，BigQuant 风格）-->
                <div class="home-left">
                    <div class="platform-header">
                        <h1>FinAgent <span>量化投研平台</span></h1>
                        <p>多智能体驱动 · 数据 · 策略 · 交易一站式平台</p>
                    </div>
                    <div class="platform-links">
                        <div class="plink" onclick="navigate('strategy')">
                            <span class="plink-icon">🤖</span>
                            <div>
                                <h3>多智能体引擎</h3>
                                <p>RAG 问答、行情、新闻、K线、简报协同</p>
                            </div>
                        </div>
                        <div class="plink" onclick="navigate('data')">
                            <span class="plink-icon">💹</span>
                            <div>
                                <h3>实时数据</h3>
                                <p>多数据源行情与财务实时获取</p>
                            </div>
                        </div>
                        <div class="plink" onclick="navigate('strategy')">
                            <span class="plink-icon">📝</span>
                            <div>
                                <h3>策略编写</h3>
                                <p>模板或中文描述，自动解析为规则</p>
                            </div>
                        </div>
                        <div class="plink" onclick="navigate('trade')">
                            <span class="plink-icon">💰</span>
                            <div>
                                <h3>模拟交易</h3>
                                <p>虚拟资金实战，手动与策略并行</p>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- 右侧：AI 对话（含会话列表）-->
                <div class="home-right">
                    <div class="card chat-card">
                        <div class="chat-layout">
                            <!-- 会话侧栏（可隐藏）-->
                            <div class="conv-sidebar" id="conv-sidebar">
                                <div class="conv-sidebar-head">
                                    <button class="btn conv-new" onclick="newConversation()">＋ 新建对话</button>
                                    <button class="btn small conv-collapse" onclick="toggleSidebar()" title="收起会话列表">☰</button>
                                </div>
                                <div class="conv-list" id="conv-list"></div>
                            </div>
                            <!-- 侧栏收起后的展开条（跟着侧栏走）-->
                            <button class="conv-toggle-collapsed" onclick="toggleSidebar()" title="展开会话列表">☰</button>
                            <!-- 聊天区 -->
                            <div class="chat-main">
                                <div class="chat-header">
                                    <h2>💬 AI 智能对话</h2>
                                </div>
                                <div class="chat-window" id="home-chat-box">
                                    <div class="chat-msg bot">你好！我是 FinAgent 助手，有什么可以帮你？可以问我股票、行情等金融问题。</div>
                                </div>
                                <div class="chat-input-bar">
                                    <input id="home-chat-input" placeholder="输入问题，如：均线策略是什么？" autocomplete="off">
                                    <button class="btn" onclick="sendHomeChat()">发送</button>
                                </div>
                                <div class="chat-quick-row">
                                    <span class="chat-quick-label">推荐策略</span>
                                    <button class="chat-quick-chip" onclick="useQuickPrompt('请介绍一下均线策略的功能和使用方法')">📈 均线策略</button>
                                    <button class="chat-quick-chip" onclick="useQuickPrompt('请介绍一下网格策略的功能和使用方法')">📊 网格策略</button>
                                    <button class="chat-quick-chip" onclick="useQuickPrompt('请介绍一下动量策略的功能和使用方法')">🚀 动量策略</button>
                                    <button class="chat-quick-chip" onclick="useQuickPrompt('请介绍一下成长因子策略的功能和使用方法')">🌱 成长因子策略</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`,

    strategy: `
        <div class="page" id="page-strategy">
            <h2>📝 编写策略</h2>
            <div class="strategy-layout">
                <div class="card">
                    <h2>选择模板</h2>
                    <div class="param-row">
                        <label>策略模板</label>
                        <select id="template-select" onchange="applyTemplate()">
                            <option value="">自定义</option>
                        </select>
                    </div>
                    <h2 style="margin-top:16px">用中文描述你的策略</h2>
                    <textarea class="editor" id="strategy-code" placeholder="例：当贵州茅台股价比20日均线低5%时买入100股，当价格涨回20日均线上方时卖出"></textarea>
                    <p style="color:#8b949e;font-size:13px;margin-top:8px">💡 用自然语言描述即可，系统会自动解析成策略规则</p>
                </div>
                <div class="card">
                    <h2>策略参数</h2>
                    <div class="param-row">
                        <label>策略名称</label>
                        <input id="strategy-name" value="我的策略">
                    </div>
                    <div class="param-row">
                        <label>标的</label>
                        <select id="strategy-symbol">
                            <option value="600519">贵州茅台 600519</option>
                            <option value="300750">宁德时代 300750</option>
                            <option value="600036">招商银行 600036</option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>初始资金</label>
                        <input id="strategy-capital" type="number" value="1000000">
                    </div>
                    <button class="btn" onclick="saveStrategy()">💾 保存并回测</button>
                    <div class="strategy-list" id="strategy-list"></div>
                </div>
            </div>
            <div class="card" id="strategy-result">
                <h2>📊 策略回测结果</h2>
                <p style="color:#888;font-size:13px">保存策略后自动显示回测结果</p>
            </div>
        </div>`,

    data: `
        <div class="page" id="page-data">
            <h2>💹 数据平台</h2>
            <div class="card">
                <div class="data-toolbar">
                    <input id="data-symbol" placeholder="股票代码，如 600519" value="600519">
                    <select id="bt-benchmark">
                        ${BENCHMARKS.map(b => `<option value="${b.code}">${b.name}</option>`).join("")}
                    </select>
                    <button class="btn tab-btn" id="btn-quote" onclick="loadQuote()">查行情</button>
                    <button class="btn tab-btn" id="btn-kline" onclick="loadKline()">看K线</button>
                    <button class="btn tab-btn" id="btn-backtest" onclick="runBacktest()">回测</button>
                    <button class="btn tab-btn" id="btn-multi" onclick="runMultiBacktest()">多股回测</button>
                </div>
                <div id="multi-config" style="display:none;margin-top:12px;gap:8px" class="data-toolbar">
                    <input id="multi-stocks" placeholder="股票池（逗号分隔）" value="600519,300750,600036,000858,600887" style="width:320px">
                    <label style="color:#666;font-size:13px">持仓数</label>
                    <input id="multi-hold" type="number" value="3" style="width:70px">
                    <label style="color:#666;font-size:13px">因子</label>
                    <select id="multi-factor">
                        <option value="momentum">动量因子</option>
                        <option value="growth">成长因子</option>
                        <option value="volatility">波动率因子</option>
                    </select>
                </div>
                <div id="data-result" style="margin-top:16px"></div>
            </div>
            <div class="card" style="margin-top:20px">
                <div class="stock-bar">
                    <h2 style="margin:0">📊 股市行情（A股）</h2>
                    <div class="stock-bar-right">
                        <input id="stock-keyword" placeholder="代码/名称筛选" style="width:140px"
                               onkeydown="if(event.key==='Enter')loadStockTable(1)">
                        <button class="btn small" onclick="loadStockTable(1)">筛选</button>
                        <button class="btn small" onclick="refreshStocks()">🔄 刷新</button>
                    </div>
                </div>
                <div class="industry-bar" id="industry-bar"><span style="color:#888;font-size:12px">行业加载中...</span></div>
                <table class="stock-table" id="stock-table">
                    <thead>
                        <tr>
                            <th>代码</th><th>名称</th>
                            <th class="sortable" onclick="toggleSort('最新价')">最新价 <span class="sort-arrow" data-col="最新价">⇅</span></th>
                            <th class="sortable" onclick="toggleSort('涨跌幅')">涨跌幅 <span class="sort-arrow" data-col="涨跌幅">⇅</span></th>
                            <th class="sortable" onclick="toggleSort('换手率')">换手率 <span class="sort-arrow" data-col="换手率">⇅</span></th>
                            <th class="sortable" onclick="toggleSort('成交额')">成交额(亿) <span class="sort-arrow" data-col="成交额">⇅</span></th>
                            <th class="sortable" onclick="toggleSort('总市值')">总市值(亿) <span class="sort-arrow" data-col="总市值">⇅</span></th>
                            <th class="sortable" onclick="toggleSort('市盈率-动态')">市盈率 <span class="sort-arrow" data-col="市盈率-动态">⇅</span></th>
                        </tr>
                    </thead>
                    <tbody id="stock-tbody"><tr><td colspan="8" style="text-align:center;color:#888">加载中...</td></tr></tbody>
                </table>
                <div class="stock-pager" id="stock-pager"></div>
                <p style="color:#999;font-size:12px;margin-top:8px">💡 点击行可将代码填入上方输入框；数据来自东方财富全市场快照，刷新后 5 分钟内复用缓存</p>
            </div>
        </div>`,

    trade: `
        <div class="page" id="page-trade">
            <h2>💰 我的交易</h2>
            <div class="card">
                <h2>当前策略</h2>
                <div id="trade-strategy">加载中...</div>
                <div style="margin-top:12px;display:flex;gap:8px">
                    <button class="btn" id="strategy-start-btn" onclick="startStrategy()">▶ 启动策略</button>
                    <button class="btn secondary" onclick="stopStrategy()">⏹ 停止策略</button>
                    <button class="btn" onclick="executeStrategy()">⚡ 执行一次</button>
                </div>
                <div id="strategy-log" style="margin-top:12px;color:#666;font-size:13px"></div>
            </div>
            <div class="stats-row" id="trade-stats"></div>
            <div class="card">
                <h2>下单</h2>
                <div class="trade-form">
                    <div class="field">
                        <label>股票代码</label>
                        <input id="trade-symbol" value="600519">
                    </div>
                    <div class="field">
                        <label>操作</label>
                        <select id="trade-side">
                            <option value="buy">买入</option>
                            <option value="sell">卖出</option>
                        </select>
                    </div>
                    <div class="field">
                        <label>数量（股）</label>
                        <input id="trade-qty" type="number" value="100">
                    </div>
                    <button class="btn buy" onclick="placeOrder()">提交订单</button>
                </div>
            </div>
            <div class="card">
                <h2>当前持仓</h2>
                <div class="positions-table" id="positions-table"></div>
            </div>
            <div class="card">
                <h2>K线图</h2>
                <div id="trade-chart" style="width:100%;height:480px"></div>
            </div>
        </div>`,
};

// ---------- 路由 ----------
function navigate(page) {
    document.querySelectorAll(".nav-link").forEach((el) =>
        el.classList.toggle("active", el.dataset.page === page)
    );
    // 首页紫色主题，其他页面默认主题
    document.body.classList.toggle("theme-purple", page === "home");
    container.innerHTML = pages[page];
    document.getElementById("page-" + page).classList.add("active");
    if (page === "trade") initTrade();
    if (page === "data") { loadStockTable(1); loadIndustries(); }  // 数据平台：自动加载股市行情 + 行业分类
    if (page === "strategy") { loadStrategyList(); loadTemplates(); }
    if (page === "home") { initHomeChat(); }}

document.querySelectorAll(".nav-link").forEach((el) =>
    el.addEventListener("click", (e) => {
        e.preventDefault();
        navigate(el.dataset.page);
    })
);

// ---------- ECharts 动态K线 ----------
function renderKline(elId, klineData) {
    if (typeof echarts === "undefined") {
        document.getElementById(elId).innerHTML =
            '<p style="color:#f85149">ECharts 加载失败：可能是 CDN 无法访问</p>';
        return;
    }
    const chart = echarts.init(document.getElementById(elId));
    const dates = klineData.dates;
    const kline = klineData.kline;
    const volumes = klineData.volumes;
    const option = {
        backgroundColor: "transparent",
        tooltip: {
            trigger: "axis",
            axisPointer: { type: "cross" },
            formatter: function (params) {
                const i = params[0].dataIndex;
                const d = dates[i];
                const k = kline[i];
                return `<b>${d}</b><br/>开盘: ${k[0]}<br/>收盘: ${k[1]}<br/>最低: ${k[2]}<br/>最高: ${k[3]}<br/>成交量: ${volumes[i]}`;
            },
        },
        legend: { data: ["K线", "成交量"], textStyle: { color: "#8b949e" } },
        grid: [
            { left: 60, right: 20, top: 20, height: "60%" },
            { left: 60, right: 20, top: "75%", height: "18%" },
        ],
        xAxis: [
            { type: "category", data: dates, gridIndex: 0, axisLabel: { color: "#8b949e" }, axisLine: { lineStyle: { color: "#30363d" } } },
            { type: "category", gridIndex: 1, data: dates, axisLabel: { show: false }, axisLine: { lineStyle: { color: "#30363d" } } },
        ],
        yAxis: [
            { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "#21262d" } } },
            { gridIndex: 1, splitLine: { show: false } },
        ],
        dataZoom: [
            { type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 },
            { type: "slider", xAxisIndex: [0, 1], bottom: 0, start: 60, end: 100 },
        ],
        series: [
            { name: "K线", type: "candlestick", data: kline, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: "#f85149", color0: "#3fb950", borderColor: "#f85149", borderColor0: "#3fb950" } },
            { name: "成交量", type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "#58a6ff" } },
        ],
    };
    chart.setOption(option);
    window.addEventListener("resize", () => chart.resize());
}

// ---------- 收益曲线图（策略 vs 基准）----------
function renderReturnsChart(elId, data) {
    const box = document.getElementById(elId);
    if (!data || !Array.isArray(data.strategy_returns) || data.strategy_returns.length === 0) {
        box.innerHTML = '<p style="color:#f85149">无回测数据（数据源可能不可用）</p>';
        return;
    }
    if (typeof echarts === "undefined") {
        box.innerHTML = '<p style="color:#f85149">ECharts 加载失败</p>';
        return;
    }
    try {
        const chart = echarts.init(box);
        // 相对收益率 = 策略收益 - 基准收益
        const relReturns = data.strategy_returns.map((v, i) =>
            v - (data.benchmark_returns[i] || 0)
        );
        // 回撤区间标注（markArea）：只在起止日期都能在 X 轴找到时才绘制（防 coord 报错）
        const dd = data.max_drawdown || {};
        const startIdx = data.dates.indexOf(dd.start);
        const endIdx = data.dates.indexOf(dd.end);
        const markArea = (startIdx >= 0 && endIdx >= 0) ? [{
            name: "最大回撤区间",
            xAxis: startIdx,
            itemStyle: { color: "rgba(248,81,73,0.08)" },
        }, {
            xAxis: endIdx,
        }] : [];
        const option = {
            backgroundColor: "transparent",
            tooltip: { trigger: "axis", valueFormatter: (v) => v + "%" },
            legend: { data: ["策略收益", "基准收益", "相对收益率"], textStyle: { color: "#8b949e" } },
            grid: { left: 60, right: 30, top: 30, bottom: 50 },
            xAxis: { type: "category", data: data.dates, axisLabel: { color: "#8b949e" }, axisLine: { lineStyle: { color: "#30363d" } } },
            yAxis: { type: "value", axisLabel: { formatter: "{value}%", color: "#8b949e" }, splitLine: { lineStyle: { color: "#21262d" } } },
            dataZoom: [
                { type: "inside", start: 0, end: 100 },
                { type: "slider", bottom: 0, start: 0, end: 100 },
            ],
            series: [
                { name: "策略收益", type: "line", data: data.strategy_returns, showSymbol: false, smooth: true,
                  lineStyle: { width: 2, color: "#f85149" }, areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(248,81,73,0.25)" }, { offset: 1, color: "rgba(248,81,73,0)" }] } } },
                { name: "基准收益", type: "line", data: data.benchmark_returns, showSymbol: false, smooth: true,
                  lineStyle: { width: 2, color: "#ffb301" } },
                { name: "相对收益率", type: "line", data: relReturns, showSymbol: false, smooth: true,
                  lineStyle: { width: 2, color: "#58a6ff" }, markArea: { data: markArea } },
            ],
        };
        chart.setOption(option);
        window.addEventListener("resize", () => chart.resize());
    } catch (e) {
        box.innerHTML = '<p style="color:#f85149">图表渲染失败：' + e.message + '</p>';
    }
}

// ---------- 数据平台 ----------
function setActiveTab(id) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    const btn = document.getElementById(id);
    if (btn) btn.classList.add("active");
}

// ---------- 股市行情列表（分页 + 行业分类 + 表头排序）----------
let stockPages = 1;
let currentIndustry = "";   // "" = 全部市场
let stockSort = { by: "", order: "desc" };   // 表头排序状态

// 点击表头三态循环：1 降序 → 2 升序 → 3 不排序（恢复默认顺序）→ 回到 1
function toggleSort(col) {
    if (stockSort.by !== col) {
        // 切到新列：默认降序
        stockSort.by = col;
        stockSort.order = "desc";
    } else if (stockSort.order === "desc") {
        // 同一列第 2 次：升序
        stockSort.order = "asc";
    } else {
        // 同一列第 3 次：取消排序，恢复默认顺序
        stockSort.by = "";
        stockSort.order = "desc";
    }
    loadStockTable(1);
}

function renderSortArrows() {
    // 箭头风格统一（线条箭头）：未排序 ⇅，降序 ↓，升序 ↑，仅高亮激活列
    document.querySelectorAll(".stock-table th.sortable").forEach(th => {
        const arrow = th.querySelector(".sort-arrow");
        const col = arrow ? arrow.dataset.col : "";
        const active = (stockSort.by === col);
        arrow.textContent = active ? (stockSort.order === "asc" ? "↑" : "↓") : "⇅";
        th.classList.toggle("sorted", active);
    });
}

function fmtNum(v) {
    return (v === null || v === undefined || v === "") ? "-" : Number(v).toFixed(2);
}
function fmtPct(v) {
    return (v === null || v === undefined || v === "") ? "-"
        : (Number(v) > 0 ? "+" : "") + Number(v).toFixed(2) + "%";
}
function fmtYi(v) {
    return (v === null || v === undefined || v === "") ? "-" : (Number(v) / 1e8).toFixed(1);
}

// 行业分类：点击行业 → 加载该行业成分股
async function loadIndustries() {
    const bar = document.getElementById("industry-bar");
    if (!bar) return;
    try {
        const resp = await apiFetch("/api/stocks/industries");
        const data = await resp.json();
        if (data.error) {
            bar.innerHTML = `<span style="color:#f85149;font-size:12px">行业加载失败：${data.error}</span>`;
            return;
        }
        bar.innerHTML = '<button class="ind-chip active" onclick="selectIndustry(\'\')">全部</button>' +
            (data.industries || []).map(n =>
                `<button class="ind-chip" onclick="selectIndustry('${String(n).replace(/'/g, "\\'")}')">${n}</button>`
            ).join("");
    } catch (e) {
        bar.innerHTML = `<span style="color:#f85149;font-size:12px">行业加载失败：${e.message}</span>`;
    }
}

function selectIndustry(name) {
    currentIndustry = name;
    document.querySelectorAll(".ind-chip").forEach(b =>
        b.classList.toggle("active", b.textContent === (name || "全部")));
    loadStockTable(1);
}

// ---------- 股票详情弹窗：点击行情行弹出，显示行情摘要 + K线 ----------
async function showStockDetail(code, name) {
    document.getElementById("stock-modal-title").textContent = `${name}（${code}）`;
    document.getElementById("stock-modal-quote").innerHTML = '<span style="color:#888">行情加载中...</span>';
    document.getElementById("stock-modal-chart").innerHTML = '';
    document.getElementById("stock-modal").style.display = "flex";
    try {
        // 并行拉实时行情 + K线
        const [qResp, kResp] = await Promise.all([
            apiFetch(`/api/quote?symbol=${code}`),
            apiFetch(`/api/kline?symbol=${code}`),
        ]);
        const q = await qResp.json();
        const k = await kResp.json();
        let pct = parseFloat(q.change_pct);
        if (isNaN(pct)) pct = 0;
        document.getElementById("stock-modal-quote").innerHTML = `
            <div class="q-item"><span class="q-label">最新价</span><span class="q-value">${q.price || "-"}</span></div>
            <div class="q-item"><span class="q-label">涨跌幅</span><span class="q-value ${pct >= 0 ? 'up' : 'down'}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span></div>
            <div class="q-item"><span class="q-label">股票名称</span><span class="q-value">${q.name || name}</span></div>
            <div class="q-item"><span class="q-label">代码</span><span class="q-value">${q.symbol || code}</span></div>`;
        renderKline("stock-modal-chart", k);
    } catch (e) {
        document.getElementById("stock-modal-quote").innerHTML =
            `<span style="color:#f85149">加载失败：${e.message}</span>`;
    }
}

function closeStockModal() {
    document.getElementById("stock-modal").style.display = "none";
}

async function loadStockTable(page = 1) {
    const kwInput = document.getElementById("stock-keyword");
    const kw = kwInput ? kwInput.value.trim() : "";
    const tbody = document.getElementById("stock-tbody");
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888">加载中...</td></tr>';
    renderSortArrows();
    const sortParam = stockSort.by ? `&sort_by=${stockSort.by}&sort_order=${stockSort.order}` : "";
    try {
        let data;
        if (currentIndustry) {
            const resp = await apiFetch(`/api/stocks/industry?name=${encodeURIComponent(currentIndustry)}&page=${page}&page_size=20${sortParam}`);
            data = await resp.json();
        } else {
            const resp = await apiFetch(`/api/stocks?page=${page}&page_size=20&keyword=${encodeURIComponent(kw)}${sortParam}`);
            data = await resp.json();
        }
        if (data.error) {
            tbody.innerHTML = `<tr><td colspan="8" style="color:#f85149">${data.error}</td></tr>`;
            return;
        }
        // 行业视图下 keyword 在当页内过滤
        let items = data.items || [];
        if (currentIndustry && kw) {
            items = items.filter(s => String(s["代码"]).includes(kw) || String(s["名称"]).includes(kw));
        }
        stockPages = data.pages;
        tbody.innerHTML = items.length ? items.map(s => `
            <tr onclick="showStockDetail('${s["代码"]}','${String(s["名称"]).replace(/'/g, "\\'")}')" title="点击查看K线">
                <td>${s["代码"]}</td>
                <td style="text-align:left">${s["名称"]}</td>
                <td>${fmtNum(s["最新价"])}</td>
                <td class="${Number(s["涨跌幅"]) >= 0 ? 'up' : 'down'}">${fmtPct(s["涨跌幅"])}</td>
                <td>${fmtPct(s["换手率"])}</td>
                <td>${fmtYi(s["成交额"])}</td>
                <td>${fmtYi(s["总市值"])}</td>
                <td>${fmtNum(s["市盈率-动态"])}</td>
            </tr>`).join("")
            : '<tr><td colspan="8" style="text-align:center;color:#888">无匹配数据</td></tr>';
        renderStockPager(data);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:#f85149">加载失败：${e.message}</td></tr>`;
    }
}

function renderStockPager(data) {
    const p = document.getElementById("stock-pager");
    if (!p) return;
    p.innerHTML = `
        <button class="btn small" ${data.page <= 1 ? 'disabled' : ''} onclick="loadStockTable(${data.page - 1})">上一页</button>
        <span style="color:#666;font-size:13px">第 <input id="stock-goto" type="number" min="1" max="${data.pages}"
            value="${data.page}" style="width:52px"> / ${data.pages} 页，共 ${data.total} 条</span>
        <button class="btn small" ${data.page >= data.pages ? 'disabled' : ''} onclick="loadStockTable(${data.page + 1})">下一页</button>
        <button class="btn small" onclick="gotoStockPage()">跳转</button>`;
}

function gotoStockPage() {
    const v = parseInt(document.getElementById("stock-goto").value, 10);
    if (v >= 1 && v <= stockPages) loadStockTable(v);
}

async function refreshStocks() {
    const tbody = document.getElementById("stock-tbody");
    if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888">正在拉取全市场数据...</td></tr>';
    try {
        const resp = await apiFetch("/api/stocks?page=1&page_size=20&refresh=true");
        const data = await resp.json();
        if (data.error) {
            if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="color:#f85149">${data.error}</td></tr>`;
            return;
        }
        loadIndustries();
        loadStockTable(1);  // 按当前视图（全部/行业）重新渲染第一页
    } catch (e) { /* 忽略，loadStockTable 会再提示 */ }
}

async function loadQuote() {
    setActiveTab("btn-quote");
    const symbol = document.getElementById("data-symbol").value;
    const box = document.getElementById("data-result");
    box.innerHTML = "加载中...";
    try {
        const resp = await apiFetch(`/api/quote?symbol=${symbol}`);
        const data = await resp.json();
        box.innerHTML = `<div class="quote-card">
            <div class="name">${data.name} (${symbol})</div>
            <div class="price">${data.price} 元</div>
            <div>涨跌幅：<span class="${data.change_pct >= 0 ? 'up' : 'down'}">${data.change_pct}%</span></div>
        </div>`;
    } catch (e) { box.innerHTML = "查询失败：" + e.message; }
}

async function loadKline() {
    setActiveTab("btn-kline");
    const symbol = document.getElementById("data-symbol").value;
    const box = document.getElementById("data-result");
    box.innerHTML = '<div id="kline-chart" style="width:100%;height:480px"></div>';
    try {
        const resp = await apiFetch(`/api/kline?symbol=${symbol}`);
        const data = await resp.json();
        renderKline("kline-chart", data);
    } catch (e) { box.innerHTML = "K线加载失败：" + e.message; }
}

async function runBacktest() {
    setActiveTab("btn-backtest");
    const symbol = document.getElementById("data-symbol").value;
    const benchmark = document.getElementById("bt-benchmark").value;
    const box = document.getElementById("data-result");
    box.innerHTML = '<div id="bt-metrics" style="margin-bottom:12px"></div><div id="bt-chart" style="width:100%;height:400px"></div><div id="bt-trades" style="margin-top:12px"></div>';
    try {
        const resp = await apiFetch(`/api/backtest?symbol=${symbol}&benchmark=${benchmark}`);
        const data = await resp.json();
        if (data.error) { box.innerHTML = `<p style="color:#f85149">${data.error}</p>`; return; }
        renderReturnsChart("bt-chart", data);
        // 指标卡片
        const dd = data.max_drawdown || {};
        const rel = data.relative_return;
        const ts = data.trade_stats || {};
        document.getElementById("bt-metrics").innerHTML =
            `<div class="stats-row">
                <div class="stat-box"><div class="label">累计收益</div><div class="value ${rel >= 0 ? 'up' : 'down'}">${data.strategy_returns[data.strategy_returns.length - 1]}%</div></div>
                <div class="stat-box"><div class="label">相对收益率</div><div class="value ${rel >= 0 ? 'up' : 'down'}">${rel}%</div></div>
                <div class="stat-box"><div class="label">年化收益</div><div class="value">${data.annualized_return}%</div></div>
                <div class="stat-box"><div class="label">夏普比率</div><div class="value">${data.sharpe}</div></div>
                <div class="stat-box"><div class="label">最大回撤</div><div class="value down">${dd.max_drawdown}%</div></div>
                <div class="stat-box"><div class="label">回撤区间</div><div class="value" style="font-size:13px">${dd.start} ~ ${dd.end}</div></div>
                <div class="stat-box"><div class="label">胜率</div><div class="value">${ts.win_rate}%</div></div>
                <div class="stat-box"><div class="label">盈亏比</div><div class="value">${ts.profit_loss_ratio}</div></div>
                <div class="stat-box"><div class="label">波动率</div><div class="value">${data.volatility}%</div></div>
            </div>`;
        const trades = data.trades || [];
        document.getElementById("bt-trades").innerHTML =
            `<table><tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th></tr>` +
            trades.map(t => `<tr><td>${t.date}</td><td>${t.side === "buy" ? "买入" : "卖出"}</td><td>${t.price}</td><td>${t.qty}</td></tr>`).join("") +
            `</table>`;
    } catch (e) { box.innerHTML = "回测失败：" + e.message; }
}

// ---------- 多股票回测 ----------
async function runMultiBacktest() {
    setActiveTab("btn-multi");
    const config = document.getElementById("multi-config");
    config.style.display = "flex";
    const stocks = document.getElementById("multi-stocks").value;
    const hold = document.getElementById("multi-hold").value;
    const factor = document.getElementById("multi-factor").value;
    const benchmark = document.getElementById("bt-benchmark").value;
    const box = document.getElementById("data-result");
    box.innerHTML = '<div id="bt-metrics" style="margin-bottom:12px"></div><div id="bt-chart" style="width:100%;height:400px"></div><div id="bt-trades" style="margin-top:12px"></div>';
    box.innerHTML += '<p style="color:#888">多股票回测中（动量因子，持仓N只每日换仓）...</p>';
    try {
        const resp = await apiFetch(`/api/backtest/multi?stocks=${encodeURIComponent(stocks)}&hold_num=${hold}&factor=${factor}&benchmark=${benchmark}`);
        const data = await resp.json();
        if (data.error) { box.innerHTML = `<p style="color:#f85149">${data.error}</p>`; return; }
        box.innerHTML = '<div id="bt-metrics" style="margin-bottom:12px"></div><div id="bt-chart" style="width:100%;height:400px"></div><div id="bt-trades" style="margin-top:12px"></div>';
        renderReturnsChart("bt-chart", data);
        const dd = data.max_drawdown || {};
        const rel = data.relative_return;
        const ts = data.trade_stats || {};
        document.getElementById("bt-metrics").innerHTML =
            `<div class="stats-row">
                <div class="stat-box"><div class="label">累计收益</div><div class="value ${rel >= 0 ? 'up' : 'down'}">${data.strategy_returns[data.strategy_returns.length - 1]}%</div></div>
                <div class="stat-box"><div class="label">相对收益率</div><div class="value ${rel >= 0 ? 'up' : 'down'}">${rel}%</div></div>
                <div class="stat-box"><div class="label">年化收益</div><div class="value">${data.annualized_return}%</div></div>
                <div class="stat-box"><div class="label">夏普比率</div><div class="value">${data.sharpe}</div></div>
                <div class="stat-box"><div class="label">最大回撤</div><div class="value down">${dd.max_drawdown}%</div></div>
                <div class="stat-box"><div class="label">胜率</div><div class="value">${ts.win_rate}%</div></div>
                <div class="stat-box"><div class="label">盈亏比</div><div class="value">${ts.profit_loss_ratio}</div></div>
            </div>`;
        const trades = data.trades || [];
        document.getElementById("bt-trades").innerHTML =
            `<table><tr><th>日期</th><th>方向</th><th>股票</th><th>价格</th><th>数量</th></tr>` +
            trades.slice(0, 30).map(t => `<tr><td>${t.date}</td><td>${t.side === "buy" ? "买入" : "卖出"}</td><td>${t.symbol}</td><td>${t.price}</td><td>${t.qty}</td></tr>`).join("") +
            (trades.length > 30 ? `<tr><td colspan="5" style="color:#888">仅显示前30笔，共${trades.length}笔</td></tr>` : "") +
            `</table>`;
    } catch (e) { box.innerHTML = "多股回测失败：" + e.message; }
}

// ---------- 策略模板 ----------
let templateCache = [];

async function loadTemplates() {
    try {
        const resp = await apiFetch("/api/strategy/templates");
        templateCache = await resp.json();
        const sel = document.getElementById("template-select");
        sel.innerHTML = '<option value="">自定义</option>' +
            templateCache.map(t => `<option value="${t.name}">${t.name}</option>`).join("");
    } catch (e) { /* 忽略 */ }
}

function applyTemplate() {
    const name = document.getElementById("template-select").value;
    const t = templateCache.find(x => x.name === name);
    if (t) {
        document.getElementById("strategy-code").value = t.default_code;
        document.getElementById("strategy-name").value = t.name;
        if (t.params && t.params.symbol) {
            document.getElementById("strategy-symbol").value = t.params.symbol;
        }
    }
}

// ---------- 策略 ----------
async function saveStrategy() {
    const strategy = {
        name: document.getElementById("strategy-name").value,
        symbol: document.getElementById("strategy-symbol").value,
        capital: document.getElementById("strategy-capital").value,
        code: document.getElementById("strategy-code").value,
    };
    const resp = await apiFetch("/api/strategy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(strategy),
    });
    const result = await resp.json();
    if (result.error) { alert(result.error); return; }
    // 设为当前策略
    await apiFetch("/api/strategy/current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(strategy),
    });
    alert("策略已保存并设为当前策略！正在回测...");
    loadStrategyList();
    // 自动回测并显示结果
    const box = document.getElementById("strategy-result");
    if (box) {
        box.innerHTML = '<div id="st-chart" style="width:100%;height:360px"></div><div id="st-metrics"></div><div id="st-trades"></div>';
        try {
            const bt = await (await apiFetch(`/api/backtest?symbol=${strategy.symbol}&rule_desc=${encodeURIComponent(strategy.code)}`)).json();
            renderReturnsChart("st-chart", bt);
            const last = bt.strategy_returns[bt.strategy_returns.length - 1];
            document.getElementById("st-metrics").innerHTML =
                `<div class="stats-row"><div class="stat-box"><div class="label">策略收益</div><div class="value">${last}%</div></div>
                 <div class="stat-box"><div class="label">基准收益</div><div class="value">${bt.benchmark_returns[bt.benchmark_returns.length - 1]}%</div></div>
                 <div class="stat-box"><div class="label">相对收益率</div><div class="value ${bt.relative_return >= 0 ? 'up' : 'down'}">${bt.relative_return}%</div></div>
                 <div class="stat-box"><div class="label">最大回撤</div><div class="value down">${bt.max_drawdown.max_drawdown}%</div></div>
                 <div class="stat-box"><div class="label">回撤区间</div><div class="value" style="font-size:13px">${bt.max_drawdown.start} ~ ${bt.max_drawdown.end}</div></div>
                 <div class="stat-box"><div class="label">期末资产</div><div class="value">${bt.final_value.toFixed(0)}</div></div></div>
                 <button class="btn" onclick="investStrategy()">💰 投入交易</button>`;
            const trades = bt.trades || [];
            document.getElementById("st-trades").innerHTML =
                `<table><tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th></tr>` +
                trades.map(t => `<tr><td>${t.date}</td><td>${t.side === "buy" ? "买入" : "卖出"}</td><td>${t.price}</td><td>${t.qty}</td></tr>`).join("") + "</table>";
        } catch (e) { box.innerHTML = "回测失败：" + e.message; }
    }
}

async function investStrategy() {
    const cur = await (await apiFetch("/api/strategy/current")).json();
    alert(`已将策略「${cur.name}」投入虚拟交易（100万），可在"我的交易"查看！`);
}

async function loadStrategyList() {
    const box = document.getElementById("strategy-list");
    try {
        const resp = await apiFetch("/api/strategy");
        const list = await resp.json();
        box.innerHTML = list.map((s) =>
            `<div class="strategy-item">
                <span>${s.name} (${s.symbol})</span>
                <span>${s.rule ? "✅ 已解析：" + (s.rule.description || s.rule.buy_trigger) : "⚠️ 未解析"}</span>
            </div>`).join("");
    } catch (e) { box.innerHTML = "加载失败"; }
}

// ---------- 我的交易 ----------
async function initTrade() {
    // 显示当前策略
    const cur = await (await apiFetch("/api/strategy/current")).json();
    document.getElementById("trade-strategy").innerHTML =
        cur.name
            ? `<p><b>${cur.name}</b>（${cur.symbol}）</p><p style="color:#888;font-size:13px">${cur.description || "无描述"}</p>`
            : '<p style="color:#888">尚未设置策略，请先到"编写策略"页保存策略</p>';
    const stats = await (await apiFetch("/api/account")).json();
    document.getElementById("trade-stats").innerHTML = `
        <div class="stat-box"><div class="label">总资产</div><div class="value">${stats.total.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">可用资金</div><div class="value">${stats.cash.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">持仓市值</div><div class="value">${stats.position_value.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">总盈亏</div><div class="value ${stats.pnl >= 0 ? 'up' : 'down'}">${stats.pnl.toFixed(2)}</div></div>`;
    loadPositions();
    loadTradeKline();
}

async function startStrategy() {
    const resp = await apiFetch("/api/strategy/start", { method: "POST" });
    const r = await resp.json();
    if (r.error) { alert(r.error); return; }
    document.getElementById("strategy-log").innerHTML = "✅ 策略已启动，每5秒自动检查执行";
    document.getElementById("strategy-start-btn").disabled = true;
}

async function stopStrategy() {
    await apiFetch("/api/strategy/stop", { method: "POST" });
    document.getElementById("strategy-log").innerHTML = "⏹ 策略已停止";
    document.getElementById("strategy-start-btn").disabled = false;
}

async function executeStrategy() {
    const resp = await apiFetch("/api/strategy/execute");
    const r = await resp.json();
    if (r.message) {
        document.getElementById("strategy-log").innerHTML = r.message;
    }
    initTrade();  // 刷新账户/持仓
}

// 策略运行中则每5秒轮询执行（仅登录后）
setInterval(async () => {
    if (!getToken()) return;  // 未登录不轮询
    try {
        const status = await (await apiFetch("/api/strategy/status")).json();
        if (status.running) {
            await executeStrategy();
        }
    } catch (e) { /* 网络错误忽略 */ }
}, 5000);

async function placeOrder() {
    const order = {
        symbol: document.getElementById("trade-symbol").value,
        side: document.getElementById("trade-side").value,
        qty: parseInt(document.getElementById("trade-qty").value),
    };
    const resp = await apiFetch("/api/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(order),
    });
    const result = await resp.json();
    alert(result.message || result.error);
    initTrade();
}

async function loadPositions() {
    const resp = await apiFetch("/api/positions");
    const list = await resp.json();
    document.getElementById("positions-table").innerHTML =
        `<table><tr><th>代码</th><th>名称</th><th>持仓量</th><th>成本</th><th>现价</th><th>盈亏</th></tr>` +
        list.map((p) => `<tr>
            <td>${p.symbol}</td><td>${p.name}</td><td>${p.qty}</td>
            <td>${p.cost}</td><td>${p.price}</td>
            <td class="${p.pnl >= 0 ? 'up' : 'down'}">${p.pnl.toFixed(2)}</td>
        </tr>`).join("") + "</table>";
}

async function loadTradeKline() {
    const symbol = document.getElementById("trade-symbol").value || "600519";
    try {
        const resp = await apiFetch(`/api/kline?symbol=${symbol}`);
        const data = await resp.json();
        renderKline("trade-chart", data);
    } catch (e) {
        document.getElementById("trade-chart").innerHTML = "K线加载失败：" + e.message;
    }
}

// 启动：校验 token → 有效进主界面，无效/无 token 显示登录页
(async function init() {
    if (!getToken()) {
        showAuthPage();
        showLogin();
        return;
    }
    try {
        // 用 token 调 /me 验证有效性
        const resp = await fetch("/api/auth/me", {
            headers: { "Authorization": "Bearer " + getToken() },
        });
        if (resp.ok) {
            showApp();
            navigate("home");
        } else {
            clearAuth();  // token 失效 → 清掉回登录页
            showAuthPage();
            showLogin();
        }
    } catch (e) {
        showAuthPage();
        showLogin();
    }
})();
