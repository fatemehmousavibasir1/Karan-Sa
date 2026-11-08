from playwright.sync_api import sync_playwright

JS = """() => {
  let e = [...document.querySelectorAll('#chatbot button')].find(x => x.innerText.includes('معوق'));
  const out = [];
  while (e && e.id !== 'chatbot') {
    const s = getComputedStyle(e);
    out.push(e.tagName + '.' + [...e.classList].join('.') + ' h=' + Math.round(e.getBoundingClientRect().height)
      + ' disp=' + s.display + ' jc=' + s.justifyContent + ' ai=' + s.alignItems);
    e = e.parentElement;
  }
  return out.join('\\n');
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    pg.goto("http://127.0.0.1:7860")
    pg.wait_for_selector("#msg textarea")
    pg.wait_for_timeout(1000)
    print(pg.evaluate(JS))
    b.close()
