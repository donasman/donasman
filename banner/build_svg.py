"""banner.html의 배치를 그대로 재서 움직이는 SVG 배너(라이트·다크)를 만든다.

실행: python banner/build_svg.py
- 글꼴은 처음 실행할 때 banner/.fonts/ 에 받아 두고, 쓰인 글자만 잘라 SVG 안에 넣는다.
- 움직임: 선이 한 번 그려진 뒤, 경험을 하나씩 돌아가며 그 경험에 쓴 기술과 선을 강조한다.
  동작 줄이기 설정을 켠 환경에서는 움직이지 않는다.
"""
import base64
import io
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "assets"
FONTS = HERE / ".fonts"
FONT_SRC = {
    "sans": ("WantedSansVariable.ttf",
             "https://cdn.jsdelivr.net/gh/wanteddev/wanted-sans@v1.0.3/packages/wanted-sans/fonts/variable/WantedSansVariable.ttf"),
    "mono": ("jetbrains-mono-500.woff",
             "https://cdn.jsdelivr.net/npm/@fontsource/jetbrains-mono@5.0.20/files/jetbrains-mono-latin-500-normal.woff"),
}

THEMES = {
    "light": dict(ink="#1f2328", muted="#59636e", rule="#d1d9e0", jade="#0e7a5f", jade_ink="#0b6650", tint="#e2f1eb"),
    "dark": dict(ink="#e6edf3", muted="#9198a1", rule="#3d444d", jade="#4cc89a", jade_ink="#6fdcb2", tint="#16352c"),
}

# 시간(초)
DRAW_STAGGER = 0.06   # 기술 행마다 선이 그려지기 시작하는 간격
DRAW_DUR = 0.9
CYCLE_DELAY = 2.2     # 첫 강조가 시작되는 시점
NEUTRAL = 1.4         # 강조 사이클 앞의 전체 보기 구간
WINDOW = 2.3          # 경험 하나를 강조하는 시간
RAMP = 0.3

MEASURE_JS = r"""
() => {
  const banner = document.querySelector('.banner');
  const base = banner.getBoundingClientRect();
  const rel = r => ({ x: r.left - base.left, y: r.top - base.top, w: r.width, h: r.height });
  const texts = [];
  const role = el => {
    if (el.closest('.name')) return ['name', 'muted'];
    if (el.closest('h1')) return ['h1', 'ink'];
    if (el.closest('.site')) return ['site', 'jade'];
    if (el.closest('.tbl')) return ['tbl', 'ink'];
    if (el.closest('.ko')) return ['ko', 'muted'];
    if (el.closest('.join')) return ['join', 'muted'];
    if (el.closest('.skills .row')) return ['skill', 'ink'];
    if (el.closest('.exps .t')) return ['xtitle', 'ink'];
    if (el.closest('.exps .sub')) return ['xsub', 'muted'];
    return ['other', 'ink'];
  };
  const walker = document.createTreeWalker(banner, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) if (walker.currentNode.textContent.trim()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const el = n.parentElement;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect();
    const mark = document.createElement('span');
    mark.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    n.parentNode.insertBefore(mark, n);
    const baseline = mark.getBoundingClientRect().bottom - base.top;
    mark.remove();
    const cs = getComputedStyle(el);
    const [kind, color] = role(el);
    const row = el.closest('.row');
    texts.push({
      text: n.textContent.trim(), x: r.left - base.left, y: baseline,
      size: parseFloat(cs.fontSize), weight: cs.fontWeight,
      mono: cs.fontFamily.includes('JetBrains'), ls: cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing),
      kind, color,
      rel: row && row.dataset.rel ? row.dataset.rel : null,
      id: row && row.dataset.id ? row.dataset.id : null,
    });
  }
  const entities = [...banner.querySelectorAll('.entity')].map(e => {
    const head = e.querySelector('.head');
    return {
      box: rel(e.getBoundingClientRect()),
      headBottom: rel(head.getBoundingClientRect()).y + head.getBoundingClientRect().height,
      rows: [...e.querySelectorAll('.row')].map(r => ({ ...rel(r.getBoundingClientRect()), rel: r.dataset.rel || null, id: r.dataset.id || null })),
    };
  });
  return { width: base.width, height: base.height, texts, entities };
}
"""

EXP_ORDER = ["work", "pitchlog", "fantasteel", "lessontree"]


def ensure_fonts():
    FONTS.mkdir(exist_ok=True)
    paths = {}
    for key, (name, url) in FONT_SRC.items():
        p = FONTS / name
        if not p.exists():
            print("download", url)
            urllib.request.urlretrieve(url, p)
        paths[key] = p
    return paths


def subset_font(path, text, flavor="woff"):
    opts = subset.Options()
    opts.flavor = flavor
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = TTFont(path)
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = flavor
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def measure():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 900, "height": 600})
        page.goto((HERE / "banner.html").resolve().as_uri())
        page.wait_for_selector("body[data-ready='1']")
        data = page.evaluate(MEASURE_JS)
        browser.close()
    return data


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def keyframes(name, members, prop_values):
    """members: 강조되는 경험 인덱스 집합. prop_values: {prop: (N, A, D)}"""
    cycle = NEUTRAL + WINDOW * len(EXP_ORDER) + RAMP
    points = [(0.0, "N"), (NEUTRAL - RAMP, "N")]
    for k in range(len(EXP_ORDER)):
        s = NEUTRAL - RAMP + WINDOW * k
        state = "A" if k in members else "D"
        points.append((s + RAMP, state))
        points.append((s + WINDOW, state))
    points.append((cycle, "N"))
    idx = {"N": 0, "A": 1, "D": 2}
    lines = [f"@keyframes {name} {{"]
    for t, st in points:
        decl = "; ".join(f"{prop}: {vals[idx[st]]}" for prop, vals in prop_values.items())
        lines.append(f"  {t / cycle * 100:.3f}% {{ {decl} }}")
    lines.append("}")
    return "\n".join(lines), cycle


def build(data, fonts_b64, theme):
    c = THEMES[theme]
    W, H = round(data["width"]), round(data["height"])
    skills_ent, exps_ent = data["entities"]
    exp_rows = {r["id"]: r for r in exps_ent["rows"]}
    exp_index = {e: i for i, e in enumerate(EXP_ORDER)}

    css, kf_done = [], {}

    def kf(kind, members, props):
        key = (kind, tuple(sorted(members)))
        if key not in kf_done:
            name = f"{kind}{len(kf_done)}"
            block, cycle = keyframes(name, set(members), props)
            css.append(block)
            kf_done[key] = (name, cycle)
        return kf_done[key]

    def cyc(kind, members, props, extra=""):
        name, cycle = kf(kind, members, props)
        anim = f"{name} {cycle:.2f}s linear {CYCLE_DELAY}s infinite"
        return f'style="animation: {extra}{anim}"'

    body = []
    # 선과 끝점
    line_props = {"opacity": (0.42, 1, 0.12), "stroke-width": ("1.15px", "1.9px", "1.15px")}
    for i, row in enumerate(skills_ent["rows"]):
        x1 = skills_ent["box"]["x"] + skills_ent["box"]["w"]
        y1 = row["y"] + row["h"] / 2
        for eid in row["rel"].split():
            er = exp_rows[eid]
            x2, y2 = er["x"], er["y"] + er["h"] / 2
            dx = (x2 - x1) * 0.5
            d = f"M{x1:.1f},{y1:.1f} C{x1 + dx:.1f},{y1:.1f} {x2 - dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            draw = f"draw {DRAW_DUR}s cubic-bezier(.3,.7,.3,1) {i * DRAW_STAGGER:.2f}s both, "
            body.append(f'<path class="ln" pathLength="1" d="{d}" {cyc("ln", [exp_index[eid]], line_props, draw)}/>')
    for row in skills_ent["rows"]:
        members = [exp_index[e] for e in row["rel"].split()]
        cx = skills_ent["box"]["x"] + skills_ent["box"]["w"]
        body.append(f'<circle class="dot" cx="{cx:.1f}" cy="{row["y"] + row["h"] / 2:.1f}" r="2" {cyc("dot", members, {"opacity": (1, 1, 0.3)})}/>')
    for eid in EXP_ORDER:
        er = exp_rows[eid]
        body.append(f'<circle class="dot" cx="{er["x"]:.1f}" cy="{er["y"] + er["h"] / 2:.1f}" r="2.6" {cyc("dot", [exp_index[eid]], {"opacity": (1, 1, 0.3)})}/>')

    # 개체 상자, 강조 배경, 구분선
    for n, ent in enumerate((skills_ent, exps_ent)):
        b = ent["box"]
        clip = f"clip{n}"
        body.append(f'<clipPath id="{clip}"><rect x="{b["x"]:.1f}" y="{b["y"]:.1f}" width="{b["w"]:.1f}" height="{b["h"]:.1f}" rx="7"/></clipPath>')
        body.append(f'<g clip-path="url(#{clip})">')
        for row in ent["rows"]:
            members = [exp_index[e] for e in row["rel"].split()] if row["rel"] else [exp_index[row["id"]]]
            body.append(f'<rect class="hl" x="{row["x"]:.1f}" y="{row["y"]:.1f}" width="{row["w"]:.1f}" height="{row["h"]:.1f}" '
                        f'{cyc("hl", members, {"opacity": (0, 1, 0)})}/>')
        body.append("</g>")
        body.append(f'<line class="rule" x1="{b["x"]:.1f}" x2="{b["x"] + b["w"]:.1f}" y1="{ent["headBottom"] - 0.5:.1f}" y2="{ent["headBottom"] - 0.5:.1f}"/>')
        for row in ent["rows"][1:]:
            body.append(f'<line class="rule" x1="{b["x"]:.1f}" x2="{b["x"] + b["w"]:.1f}" y1="{row["y"] + 0.5:.1f}" y2="{row["y"] + 0.5:.1f}"/>')
        body.append(f'<rect class="box" x="{b["x"] + 0.5:.1f}" y="{b["y"] + 0.5:.1f}" width="{b["w"] - 1:.1f}" height="{b["h"] - 1:.1f}" rx="6.5"/>')

    # 글자
    for t in data["texts"]:
        fam = "m" if t["mono"] else "s"
        attrs = f'x="{t["x"]:.2f}" y="{t["y"]:.2f}" class="{fam} {t["color"]}" font-size="{t["size"]}" font-weight="{t["weight"]}"'
        if t["ls"]:
            attrs += f' letter-spacing="{t["ls"]:.3f}"'
        if t["kind"] == "skill":
            members = [exp_index[e] for e in t["rel"].split()]
            attrs += " " + cyc("tx", members, {"fill": (c["ink"], c["jade_ink"], c["muted"])})
        elif t["kind"] == "xtitle":
            attrs += " " + cyc("tx", [exp_index[t["id"]]], {"fill": (c["ink"], c["jade_ink"], c["muted"])})
        body.append(f"<text {attrs}>{esc(t['text'])}</text>")

    style = f"""
@font-face {{ font-family: "B Sans"; src: url(data:font/woff;base64,{fonts_b64['sans']}) format("woff"); font-weight: 400 1000; }}
@font-face {{ font-family: "B Mono"; src: url(data:font/woff;base64,{fonts_b64['mono']}) format("woff"); font-weight: 500; }}
.s {{ font-family: "B Sans", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; }}
.m {{ font-family: "B Mono", ui-monospace, monospace; }}
.ink {{ fill: {c['ink']}; }} .muted {{ fill: {c['muted']}; }} .jade {{ fill: {c['jade']}; }}
.box {{ fill: none; stroke: {c['rule']}; stroke-width: 1; }}
.rule {{ stroke: {c['rule']}; stroke-width: 1; }}
.hl {{ fill: {c['tint']}; opacity: 0; }}
.ln {{ fill: none; stroke: {c['jade']}; stroke-width: 1.15px; opacity: .42; stroke-dasharray: 1; stroke-dashoffset: 0; }}
.dot {{ fill: {c['jade']}; }}
@keyframes draw {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
{chr(10).join(css)}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
"""
    label = "정건희, 데이터가 어긋나지 않는 구조를 만드는 백엔드 개발자. 기술 14개를 실무 1건과 프로젝트 3건에 연결한 관계도"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{label}">\n'
            f"<title>{label}</title>\n<style>{style}</style>\n" + "\n".join(body) + "\n</svg>\n")


def main():
    fonts = ensure_fonts()
    data = measure()
    sans_text = "".join(t["text"] for t in data["texts"] if not t["mono"])
    mono_text = "".join(t["text"] for t in data["texts"] if t["mono"])
    fonts_b64 = {"sans": subset_font(fonts["sans"], sans_text), "mono": subset_font(fonts["mono"], mono_text)}
    for theme in THEMES:
        svg = build(data, fonts_b64, theme)
        out = OUT / f"banner-{theme}.svg"
        out.write_text(svg, encoding="utf-8")
        print("saved", out, f"{len(svg.encode('utf-8')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
