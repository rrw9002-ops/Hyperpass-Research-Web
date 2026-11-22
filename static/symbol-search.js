"use strict";
(() => {
  const qualified = /^[A-Z0-9_]+:[A-Z0-9.^=_!-]+$/;
  const get = id => document.getElementById(id);
  let selection = null;

  function selected() {
    const value = get("tv-symbol").value.trim();
    if (selection && value === selection.name) return selection.id;
    if (qualified.test(value.toUpperCase())) return value.toUpperCase();
    throw new Error("종목명 또는 티커를 입력하고 검색 결과에서 거래소와 종목을 선택하세요.");
  }

  function mount() {
    const input = get("tv-symbol"), matches = get("tv-symbol-matches"), status = get("tv-symbol-status");
    if (!input || !matches || !status) return;
    let timer, version = 0, composing = false;

    function choose(item) {
      if (input.disabled) return;
      ++version;
      clearTimeout(timer);
      selection = item;
      input.value = item.name;
      matches.replaceChildren();
      status.textContent = "선택한 종목 · " + item.id;
      input.focus();
    }

    async function search(query, request) {
      try {
        const data = await window.HyperpassApp.api("/api/tradingview/symbols?q=" + encodeURIComponent(query));
        if (request !== version || input.value.trim() !== query) return;
        const results = data.results || [];
        for (const item of results) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "button ghost compact";
          button.textContent = item.name + " · " + item.id;
          button.addEventListener("click", () => choose(item));
          matches.append(button);
        }
        const message = results.length ? "거래소와 종목을 확인한 뒤 선택하세요." : "일치하는 종목이 없습니다. 다른 이름이나 티커를 입력하세요.";
        status.textContent = [message, data.notice].filter(Boolean).join(" ");
      } catch (error) {
        if (request === version) status.textContent = error.message || "종목 검색에 연결하지 못했습니다.";
      }
    }

    function update() {
      ++version;
      clearTimeout(timer);
      selection = null;
      matches.replaceChildren();
      const query = input.value.trim();
      if (!query || composing) {
        status.textContent = "";
      } else if (qualified.test(query.toUpperCase())) {
        status.textContent = "직접 입력한 종목 · " + query.toUpperCase();
      } else {
        status.textContent = "종목을 찾고 있습니다…";
        const request = version;
        timer = setTimeout(() => search(query, request), 300);
      }
    }
    input.addEventListener("input", update);
    input.addEventListener("compositionstart", () => { composing = true; update(); });
    input.addEventListener("compositionend", () => { composing = false; update(); });
    input.addEventListener("keydown", event => {
      if (!event.isComposing && ["ArrowDown", "Enter"].includes(event.key) && matches.firstChild) {
        event.preventDefault();
        matches.firstChild.focus();
      }
    });
  }
  window.HyperpassSymbols = {selected};
  document.addEventListener("DOMContentLoaded", mount, {once: true});
})();
