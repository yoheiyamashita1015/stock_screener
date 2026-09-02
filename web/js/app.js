"use strict";

const API_URL =
  "https://axkd5z9qdd.execute-api.ap-northeast-1.amazonaws.com/screen";
const MAX_DISPLAY_ROWS = 100;

const form = document.querySelector("#screening-form");
const searchButton = document.querySelector("#search-button");
const resetButton = document.querySelector("#reset-button");
const formMessage = document.querySelector("#form-message");
const includeTechnicals = document.querySelector("#include-technicals");
const technicalFields = document.querySelector("#technical-fields");
const resultSummary = document.querySelector("#result-summary");
const resultsBody = document.querySelector("#results-body");
const tableWrap = document.querySelector("#table-wrap");
const emptyState = document.querySelector("#empty-state");
const sortOrder = document.querySelector("#sort-order");

let latestStocks = [];

const numericConditions = {
  "min-market-cap": { key: "min_market_cap", multiplier: 1_000_000_000 },
  "max-market-cap": { key: "max_market_cap", multiplier: 1_000_000_000 },
  "min-per": { key: "min_per" },
  "max-per": { key: "max_per" },
  "min-pbr": { key: "min_pbr" },
  "max-pbr": { key: "max_pbr" },
  "min-dividend-yield": { key: "min_dividend_yield" },
  "max-dividend-yield": { key: "max_dividend_yield" },
  "min-roe": { key: "min_roe" },
  "min-roa": { key: "min_roa" },
  "min-revenue-growth": { key: "min_revenue_growth" },
  "min-eps-growth": { key: "min_eps_growth" },
  "min-eps-consecutive-years": { key: "min_eps_consecutive_years" },
  "min-fcf-yield": { key: "min_fcf_yield" },
  "min-insider-hold": { key: "min_insider_hold" },
  "max-insider-hold": { key: "max_insider_hold" },
  "min-rsi": { key: "min_rsi", technical: true },
  "max-rsi": { key: "max_rsi", technical: true },
  "min-pct-from-52w-high": {
    key: "min_pct_from_52w_high",
    technical: true,
  },
  "max-pct-from-52w-high": {
    key: "max_pct_from_52w_high",
    technical: true,
  },
};

const rangePairs = [
  ["min-market-cap", "max-market-cap", "時価総額"],
  ["min-per", "max-per", "PER"],
  ["min-pbr", "max-pbr", "PBR"],
  ["min-dividend-yield", "max-dividend-yield", "配当利回り"],
  ["min-insider-hold", "max-insider-hold", "インサイダー保有率"],
  ["min-rsi", "max-rsi", "RSI"],
  [
    "min-pct-from-52w-high",
    "max-pct-from-52w-high",
    "52週高値からの乖離",
  ],
];

function readNumber(id) {
  const element = document.querySelector(`#${id}`);
  if (element.value.trim() === "") {
    return null;
  }
  const value = Number(element.value);
  return Number.isFinite(value) ? value : null;
}

function buildConditions() {
  const conditions = {};

  Object.entries(numericConditions).forEach(([id, definition]) => {
    if (definition.technical && !includeTechnicals.checked) {
      return;
    }
    const value = readNumber(id);
    if (value !== null) {
      conditions[definition.key] = value * (definition.multiplier ?? 1);
    }
  });

  const sector = document.querySelector("#sector").value;
  if (sector) {
    conditions.sectors = [sector];
  }

  if (includeTechnicals.checked) {
    [20, 50, 200].forEach((period) => {
      const value = document.querySelector(`#above-sma-${period}`).value;
      if (value) {
        conditions[`above_sma_${period}`] = value === "true";
      }
    });

    const trend = document.querySelector("#trend-signal").value;
    if (trend) {
      conditions.trend_signals = [trend];
    }
  }

  return conditions;
}

function validateConditions() {
  for (const [minimumId, maximumId, label] of rangePairs) {
    if (!includeTechnicals.checked && numericConditions[minimumId]?.technical) {
      continue;
    }
    const minimum = readNumber(minimumId);
    const maximum = readNumber(maximumId);
    if (minimum !== null && maximum !== null && minimum > maximum) {
      return `${label}は、最小値を最大値以下にしてください。`;
    }
  }

  if (!form.checkValidity()) {
    return "入力値の範囲を確認してください。";
  }
  return "";
}

function setLoading(isLoading) {
  searchButton.disabled = isLoading;
  resetButton.disabled = isLoading;
  searchButton.classList.toggle("is-loading", isLoading);
  searchButton.querySelector(".button-label").textContent = isLoading
    ? "検索中"
    : "銘柄を検索";
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat("ja-JP", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

function formatPercent(value, digits = 1) {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted}%`;
}

function formatMarketCap(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "—";
  }
  if (number >= 1_000_000_000_000) {
    return `$${formatNumber(number / 1_000_000_000_000, 2)}T`;
  }
  if (number >= 1_000_000_000) {
    return `$${formatNumber(number / 1_000_000_000, 2)}B`;
  }
  if (number >= 1_000_000) {
    return `$${formatNumber(number / 1_000_000, 1)}M`;
  }
  return `$${formatNumber(number, 0)}`;
}

function createCell(text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) {
    cell.className = className;
  }
  return cell;
}

function createTickerCell(stock) {
  const cell = document.createElement("td");
  const link = document.createElement("a");
  link.className = "ticker-link";
  link.href = `https://finance.yahoo.com/quote/${encodeURIComponent(stock.ticker)}`;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = stock.ticker ?? "—";
  cell.append(link);
  return cell;
}

function createNameCell(stock) {
  const cell = document.createElement("td");
  const name = document.createElement("span");
  name.className = "company-name";
  name.textContent = stock.name || "—";
  name.title = stock.name || "";
  cell.append(name);
  return cell;
}

function createTrendCell(value) {
  const cell = document.createElement("td");
  if (!value) {
    cell.textContent = "—";
    return cell;
  }
  const badge = document.createElement("span");
  badge.className = `trend-badge trend-${value.toLowerCase().replaceAll("_", "-")}`;
  badge.textContent = value.replaceAll("_", " ");
  cell.append(badge);
  return cell;
}

function sortedStocks() {
  const [key, direction] = sortOrder.value.split("-");
  const factor = direction === "asc" ? 1 : -1;

  return [...latestStocks].sort((left, right) => {
    const leftValue = Number(left[key]);
    const rightValue = Number(right[key]);
    const leftValid = Number.isFinite(leftValue);
    const rightValid = Number.isFinite(rightValue);
    if (!leftValid && !rightValid) return 0;
    if (!leftValid) return 1;
    if (!rightValid) return -1;
    return (leftValue - rightValue) * factor;
  });
}

function renderResults() {
  resultsBody.replaceChildren();
  const visibleStocks = sortedStocks().slice(0, MAX_DISPLAY_ROWS);

  visibleStocks.forEach((stock) => {
    const row = document.createElement("tr");
    row.append(
      createTickerCell(stock),
      createNameCell(stock),
      createCell(stock.sector || "—"),
      createCell(formatNumber(stock.current_price, 2), "numeric"),
      createCell(formatMarketCap(stock.market_cap), "numeric"),
      createCell(formatNumber(stock.per, 2), "numeric"),
      createCell(formatNumber(stock.pbr, 2), "numeric"),
      createCell(formatPercent(stock.roe, 1), "numeric"),
      createCell(formatPercent(stock.revenue_growth, 1), "numeric"),
      createCell(formatPercent(stock.eps_growth_rate, 1), "numeric"),
      createCell(formatPercent(stock.dividend_yield, 2), "numeric"),
      createCell(formatNumber(stock.rsi, 1), "numeric"),
      createTrendCell(stock.trend_signal),
    );
    resultsBody.append(row);
  });

  const hasResults = latestStocks.length > 0;
  tableWrap.hidden = !hasResults;
  emptyState.hidden = hasResults;
  sortOrder.disabled = !hasResults;

  if (hasResults) {
    const displayed = Math.min(latestStocks.length, MAX_DISPLAY_ROWS);
    resultSummary.textContent = `${latestStocks.length.toLocaleString("ja-JP")}件中 ${displayed.toLocaleString("ja-JP")}件を表示しています。`;
  } else {
    emptyState.querySelector("strong").textContent = "条件に合う銘柄はありませんでした";
    emptyState.querySelector("p").textContent = "条件を緩めて、もう一度検索してください。";
    resultSummary.textContent = "該当銘柄は0件です。";
  }
}

async function requestScreening(payload) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 25_000);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("APIから正しいJSONが返されませんでした。");
    }

    if (!response.ok) {
      throw new Error(data.error || `APIエラーが発生しました（${response.status}）。`);
    }
    if (!Array.isArray(data.stocks)) {
      throw new Error("APIレスポンスの形式が正しくありません。");
    }
    return data;
  } finally {
    window.clearTimeout(timeout);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "";

  const validationError = validateConditions();
  if (validationError) {
    formMessage.textContent = validationError;
    return;
  }

  const conditions = buildConditions();
  if (Object.keys(conditions).length === 0) {
    formMessage.textContent = "少なくとも1つの検索条件を指定してください。";
    return;
  }

  setLoading(true);
  resultSummary.textContent = "S3の最新データを検索しています…";

  try {
    const data = await requestScreening({
      conditions,
      include_technicals: includeTechnicals.checked,
    });
    latestStocks = data.stocks;
    renderResults();
    document.querySelector("#results-section").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  } catch (error) {
    latestStocks = [];
    tableWrap.hidden = true;
    emptyState.hidden = false;
    sortOrder.disabled = true;
    emptyState.querySelector("strong").textContent = "検索に失敗しました";
    emptyState.querySelector("p").textContent =
      error.name === "AbortError"
        ? "応答がタイムアウトしました。しばらく待って再実行してください。"
        : error.message;
    resultSummary.textContent = "APIとの通信を確認してください。";
  } finally {
    setLoading(false);
  }
});

form.addEventListener("reset", () => {
  window.setTimeout(() => {
    includeTechnicals.checked = true;
    technicalFields.disabled = false;
    formMessage.textContent = "";
  });
});

includeTechnicals.addEventListener("change", () => {
  technicalFields.disabled = !includeTechnicals.checked;
});

sortOrder.addEventListener("change", renderResults);
