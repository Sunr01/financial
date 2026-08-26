// FinAgent 量化平台：SPA 路由 + 页面逻辑
const container = document.getElementById("page-container");

// ---------- 页面模板 ----------
const pages = {
    home: `
        <div class="page" id="page-home">
            <div class="hero">
                <h1>FinAgent <span>量化投研平台</span></h1>
                <p>多智能体驱动 · 数据 · 策略 · 交易一站式平台</p>
                <button class="btn" onclick="navigate('strategy')">开始编写策略</button>
                <button class="btn secondary" onclick="navigate('data')">浏览数据</button>
            </div>
            <div class="features">
                <div class="feature-card">
                    <div class="icon">🤖</div>
                    <h3>多智能体引擎</h3>
                    <p>RAG 问答、行情、新闻、K线、简报五大 Agent 协同工作</p>
                </div>
                <div class="feature-card">
                    <div class="icon">💹</div>
                    <h3>实时数据</h3>
                    <p>新浪/腾讯/东财多数据源，行情与财务数据实时获取</p>
                </div>
                <div class="feature-card">
                    <div class="icon">📝</div>
                    <h3>策略编写</h3>
                    <p>中文描述交易策略，自动解析为规则，无需写代码</p>
                </div>
                <div class="feature-card">
                    <div class="icon">💰</div>
                    <h3>模拟交易</h3>
                    <p>虚拟资金实战演练，手动与策略并行交易</p>
                </div>
            </div>
        </div>`,

    strategy: `
        <div class="page" id="page-strategy">
            <h2>📝 编写策略</h2>
            <div class="strategy-layout">
                <div class="card">
                    <h2>用中文描述你的策略</h2>
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
                    <button class="btn" onclick="saveStrategy()">💾 保存策略</button>
                    <div class="strategy-list" id="strategy-list"></div>
                </div>
            </div>
        </div>`,

    data: `
        <div class="page" id="page-data">
            <h2>💹 数据平台</h2>
            <div class="card">
                <div class="data-toolbar">
                    <input id="data-symbol" placeholder="股票代码，如 600519" value="600519">
                    <button class="btn" onclick="loadQuote()">查询行情</button>
                    <button class="btn secondary" onclick="loadKline()">查看K线</button>
                </div>
                <div id="quote-result"></div>
                <div id="kline-chart" style="width:100%;height:480px;margin-top:16px"></div>
            </div>
        </div>`,

    trade: `
        <div class="page" id="page-trade">
            <h2>💰 我的交易</h2>
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
    container.innerHTML = pages[page];
    document.getElementById("page-" + page).classList.add("active");
    if (page === "trade") initTrade();
    if (page === "data") loadQuote();
    if (page === "strategy") loadStrategyList();
}

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
            { type: "category", data: dates, gridIndex: 0,
              axisLabel: { color: "#8b949e" }, axisLine: { lineStyle: { color: "#30363d" } } },
            { type: "category", gridIndex: 1, data: dates,
              axisLabel: { show: false }, axisLine: { lineStyle: { color: "#30363d" } } },
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
            {
                name: "K线", type: "candlestick", data: kline, xAxisIndex: 0, yAxisIndex: 0,
                itemStyle: {
                    color: "#f85149", color0: "#3fb950",
                    borderColor: "#f85149", borderColor0: "#3fb950",
                },
            },
            {
                name: "成交量", type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1,
                itemStyle: { color: "#58a6ff" },
            },
        ],
    };
    chart.setOption(option);
    window.addEventListener("resize", () => chart.resize());
}

// ---------- 数据平台 ----------
async function loadQuote() {
    const symbol = document.getElementById("data-symbol").value;
    const box = document.getElementById("quote-result");
    box.innerHTML = "加载中...";
    try {
        const resp = await fetch(`/api/quote?symbol=${symbol}`);
        const data = await resp.json();
        box.innerHTML = `<div class="quote-card">
            <div class="name">${data.name} (${symbol})</div>
            <div class="price">${data.price} 元</div>
            <div>涨跌幅：<span class="${data.change_pct >= 0 ? 'up' : 'down'}">${data.change_pct}%</span></div>
        </div>`;
    } catch (e) {
        box.innerHTML = "查询失败：" + e.message;
    }
}

async function loadKline() {
    const symbol = document.getElementById("data-symbol").value;
    const box = document.getElementById("kline-chart");
    box.innerHTML = "加载中...";
    try {
        const resp = await fetch(`/api/kline?symbol=${symbol}`);
        const data = await resp.json();
        renderKline("kline-chart", data);
    } catch (e) {
        box.innerHTML = "K线加载失败：" + e.message;
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
    const resp = await fetch("/api/strategy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(strategy),
    });
    const result = await resp.json();
    alert(result.error || "策略已保存并解析为规则！");
    loadStrategyList();
}

async function loadStrategyList() {
    const box = document.getElementById("strategy-list");
    try {
        const resp = await fetch("/api/strategy");
        const list = await resp.json();
        box.innerHTML = list.map((s) =>
            `<div class="strategy-item">
                <span>${s.name} (${s.symbol})</span>
                <span>${s.rule ? "✅ 已解析：" + (s.rule.description || s.rule.buy_trigger) : "⚠️ 未解析"}</span>
            </div>`).join("");
    } catch (e) {
        box.innerHTML = "加载失败";
    }
}

// ---------- 我的交易 ----------
async function initTrade() {
    const stats = await (await fetch("/api/account")).json();
    document.getElementById("trade-stats").innerHTML = `
        <div class="stat-box"><div class="label">总资产</div><div class="value">${stats.total.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">可用资金</div><div class="value">${stats.cash.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">持仓市值</div><div class="value">${stats.position_value.toFixed(2)}</div></div>
        <div class="stat-box"><div class="label">总盈亏</div><div class="value ${stats.pnl >= 0 ? 'up' : 'down'}">${stats.pnl.toFixed(2)}</div></div>`;
    loadPositions();
    loadTradeKline();
}

async function placeOrder() {
    const order = {
        symbol: document.getElementById("trade-symbol").value,
        side: document.getElementById("trade-side").value,
        qty: parseInt(document.getElementById("trade-qty").value),
    };
    const resp = await fetch("/api/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(order),
    });
    const result = await resp.json();
    alert(result.message || result.error);
    initTrade();
}

async function loadPositions() {
    const resp = await fetch("/api/positions");
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
        const resp = await fetch(`/api/kline?symbol=${symbol}`);
        const data = await resp.json();
        renderKline("trade-chart", data);
    } catch (e) {
        document.getElementById("trade-chart").innerHTML = "K线加载失败：" + e.message;
    }
}

// 默认进入首页
navigate("home");
