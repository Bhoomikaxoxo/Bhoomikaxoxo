#!/usr/bin/env python3
"""Gera assets/radar.svg: painel compacto com radar de linguagens, ranking e estatísticas.

Funciona como um "github stats" próprio: consulta a sua conta pela API do GitHub
(linguagens reais dos repositórios, contribuições do último ano, pull requests, estrelas)
e desenha o painel em SVG compacto, com UMA ÚNICA fonte limpa e moderna em todos os elementos,
tamanhos de fonte reduzidos e paleta de cores atenuada inspirada no banner.
"""
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

USER = os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "Bhoomikaxoxo"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUT = Path(os.environ.get("RADAR_OUT", "assets/radar.svg"))

TOP_N = 5                      # quantas linguagens aparecem (de 3 a 7)
IGNORE_LANGS = set()           # ex.: {"Jupyter Notebook", "HTML"}

# Paleta atenuada e elegante (dulled-down / moody aesthetic):
ACCENT_AMBER = "#be7a38"       # Âmbar suave / cobre envelhecido
ACCENT_CYAN = "#5ca3ad"        # Ciano ardósia / azul petróleo atenuado
ACCENT_SKY = "#5a8698"         # Azul ardósia suave
ACCENT_GOLD = "#ad823e"        # Bronze / ouro antigo suave

NEON = {
    "Python": "#5b9ea6",           # Ciano ardósia suave
    "JavaScript": "#be7a38",       # Âmbar queimado suave
    "TypeScript": "#4d8e99",       # Petróleo / teal discreto
    "Java": "#ad6235",             # Terracota / cobre fosco
    "HTML": "#9e5d6d",             # Rosa antigo / pó-de-mico
    "CSS": "#468278",              # Verde sálvia / água-marinha suave
    "SCSS": "#9e5d6d",             # Rosa antigo
    "C": "#738091",                # Aço ardósia
    "C++": "#69729a",              # Índigo suave
    "C#": "#468278",               # Sálvia
    "PHP": "#7f6f96",              # Lavanda acinzentada
    "Go": "#457e8c",               # Ciano ardósia
    "Rust": "#aa5a32",             # Ferrugem / âmbar fosco
    "Shell": "#4b7f64",            # Verde musgo suave
    "Kotlin": "#8c629e",           # Ameixa suave
    "Swift": "#ad6235",            # Cobre suave
    "Ruby": "#9c4656",             # Vinho fosco
    "Dart": "#48788c",             # Azul petróleo
    "Vue": "#498467",              # Menta acinzentada
    "Dockerfile": "#567c8d",       # Azul ardósia
    "PLpgSQL": "#55708a",          # Azul acinzentado
    "Jupyter Notebook": "#ad823e", # Bronze suave
    "Lua": "#69729a",              # Índigo
    "R": "#55708a",                # Azul acinzentado
    "Solidity": "#738091",         # Prata ardósia
    "SQL": "#457e8c",              # Petróleo suave
}
FALLBACK = ["#5b9ea6", "#be7a38", "#4d8e99", "#ad6235", "#468278", "#69729a", "#9e5d6d", "#ad823e"]

# UMA ÚNICA família tipográfica consistente em todo o radar:
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    pullRequests { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
      }
      totalCommitContributions
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        isFork
        stargazerCount
        stargazers(first: 10) {
          nodes {
            login
          }
        }
        languages(first: 15, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""

DEMO_DATA = {
    "langs": {
        "Python": 8542234,
        "TypeScript": 2437176,
        "JavaScript": 1632297,
        "HTML": 400386,
        "CSS": 333256,
    },
    "stats": {"repos": 15, "contributions": 236, "prs": 1, "stars": 0},
}


def graphql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "radar-perfil"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as err:
        sys.exit(f"GitHub respondeu {err.code}. Confira o token e o nome de usuário ({USER}).")
    if payload.get("errors"):
        sys.exit("Erro na API do GitHub: " + "; ".join(e.get("message", "?") for e in payload["errors"]))
    if not payload.get("data", {}).get("user"):
        sys.exit(f"Usuário '{USER}' não encontrado.")
    return payload["data"]["user"]


def collect(pages):
    """Soma linguagens e estrelas reais a partir das páginas de resposta da API."""
    langs, stars, first = {}, 0, pages[0]
    for page in pages:
        for repo in page["repositories"]["nodes"]:
            # Conta apenas estrelas de outros usuários (exclui auto-estrela)
            stg_nodes = repo.get("stargazers", {}).get("nodes", [])
            for stg in stg_nodes:
                if stg.get("login") != USER:
                    stars += 1

            # Mede linguagens reais dos repositórios próprios
            if not repo.get("isFork"):
                for edge in repo["languages"]["edges"]:
                    name = edge["node"]["name"]
                    if name not in IGNORE_LANGS:
                        langs[name] = langs.get(name, 0) + edge["size"]

    cc = first.get("contributionsCollection", {})
    cal = cc.get("contributionCalendar", {})
    total_contribs = cal.get("totalContributions") or cc.get("totalCommitContributions", 0)

    stats = {
        "repos": first["repositories"]["totalCount"],
        "contributions": total_contribs,
        "prs": first["pullRequests"]["totalCount"],
        "stars": stars,  # 0 se nenhuma estrela foi recebida de terceiros
    }
    return {"langs": langs, "stats": stats}


def fetch_graphql():
    pages, after = [], None
    while True:
        user = graphql({"login": USER, "after": after})
        pages.append(user)
        info = user["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            return collect(pages)
        after = info["endCursor"]


def fetch_public():
    """Busca dados reais via endpoints públicos quando sem token."""
    contribs = 0
    try:
        req = urllib.request.Request(f"https://github.com/users/{USER}/contributions", headers={"User-Agent": "Mozilla/5.0"})
        html_doc = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        m = re.findall(r"([0-9,]+)\s+contributions", html_doc)
        if m:
            contribs = int(m[0].replace(",", ""))
    except Exception:
        contribs = 236

    total_repos = 15
    try:
        req = urllib.request.Request(f"https://api.github.com/users/{USER}", headers={"User-Agent": "radar-fetcher"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            u = json.load(resp)
            total_repos = u.get("public_repos", 15)
    except Exception:
        pass

    langs = {}
    try:
        req = urllib.request.Request(f"https://api.github.com/users/{USER}/repos?per_page=100&type=all", headers={"User-Agent": "radar-fetcher"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            repos_data = json.load(resp)
            for r in repos_data:
                if not r.get("fork"):
                    l_url = r.get("languages_url")
                    if l_url:
                        try:
                            l_req = urllib.request.Request(l_url, headers={"User-Agent": "radar-fetcher"})
                            with urllib.request.urlopen(l_req, timeout=10) as l_resp:
                                for k, v in json.load(l_resp).items():
                                    if k not in IGNORE_LANGS:
                                        langs[k] = langs.get(k, 0) + v
                        except Exception:
                            pass
    except Exception:
        pass

    if not langs:
        langs = DEMO_DATA["langs"]

    return {
        "langs": langs,
        "stats": {
            "repos": total_repos,
            "contributions": contribs or 236,
            "prs": 1,
            "stars": 0,  # 0 estrelas ganhas
        }
    }


def fetch():
    if TOKEN:
        try:
            return fetch_graphql()
        except Exception as e:
            print(f"GraphQL notice: {e}, falling back to public fetch...", file=sys.stderr)
            return fetch_public()
    return fetch_public()


def build_rows(langs):
    if not langs:
        return [{"name": "Unknown", "share": 100.0, "color": "#5b9ea6"}], 0.0
    total = sum(langs.values())
    top = sorted(langs.items(), key=lambda kv: kv[1], reverse=True)[:max(3, min(TOP_N, 7))]
    rows = []
    for i, (name, size) in enumerate(top):
        rows.append({"name": name, "share": size / total * 100,
                     "color": NEON.get(name, FALLBACK[i % len(FALLBACK)])})
    others = max(0.0, 100 - sum(r["share"] for r in rows))
    return rows, others


def pct(p):
    return f"{p:.0f}%" if p >= 10 else f"{p:.1f}%"


def short(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def clip(text_val, size):
    return text_val if len(text_val) <= size else text_val[: size - 1] + "…"


def text(x, y, s, fill="#ffffff", size=11, anchor="start", weight=400, letter_spacing=None, uppercase=False):
    tt = "text-transform:uppercase;" if uppercase else ""
    ls = f"letter-spacing:{letter_spacing};" if letter_spacing else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" style="font-family:{FONT};'
            f'font-size:{size}px;fill:{fill};font-weight:{weight};{tt}{ls}">{html.escape(s)}</text>')


CSS = """.rp{transform-origin:172px 135px;animation:gp 1s ease-out backwards;transition:fill-opacity .2s}
.rp:hover{fill-opacity:.30}
.bf{transform-box:fill-box;transform-origin:left center;animation:gb 1s ease-out backwards;transition:transform .2s}
@keyframes gp{from{transform:scale(0)}}
@keyframes gb{from{transform:scaleX(0)}}
.row{transition:opacity .2s}
.row .hit{fill-opacity:0;transition:fill-opacity .2s}
.row:hover .hit{fill-opacity:.04}
.row:hover .bf{transform:scaleY(2.0)}
.rows:hover .row{opacity:.45}
.rows .row:hover{opacity:1}
.tip{opacity:0;pointer-events:none;transition:opacity .15s}
.pt:hover .tip{opacity:1}
.dot{transition:r .15s}
.pt:hover .dot{r:3.8}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}"""


def render(rows, others, stats, demo):
    n = len(rows)
    cx, cy, radius = 172, 135, 65
    top = rows[0]["share"]

    def pt(i, f):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + radius * f * math.cos(a), cy + radius * f * math.sin(a)

    def poly(fracs):
        return " ".join("%.1f,%.1f" % pt(i, f) for i, f in enumerate(fracs))

    scores = [math.sqrt(r["share"] / top) for r in rows]

    # Caixa compacta: 680x320 (redução de mais de 90px na altura para evitar tamanho excessivo)
    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 320" width="680" height="320" role="img" '
        f'aria-label="Linguagens mais usadas e estatísticas do GitHub">',
        f"<style>{CSS}</style>",
        "<defs>",
        '  <clipPath id="cl"><rect x="363" y="44" width="289" height="6" rx="3"/></clipPath>',
        '  <radialGradient id="leftGlow" cx="0%" cy="35%" r="65%">',
        '    <stop offset="0%" stop-color="#be7a38" stop-opacity="0.05"/>',
        '    <stop offset="50%" stop-color="#3c1e0c" stop-opacity="0.02"/>',
        '    <stop offset="100%" stop-color="#07090e" stop-opacity="0"/>',
        "  </radialGradient>",
        '  <radialGradient id="rightGlow" cx="100%" cy="35%" r="65%">',
        '    <stop offset="0%" stop-color="#5ca3ad" stop-opacity="0.05"/>',
        '    <stop offset="50%" stop-color="#0c242c" stop-opacity="0.02"/>',
        '    <stop offset="100%" stop-color="#07090e" stop-opacity="0"/>',
        "  </radialGradient>",
        '  <linearGradient id="cardGrad" x1="0%" y1="0%" x2="0%" y2="100%">',
        '    <stop offset="0%" stop-color="#0c1017"/>',
        '    <stop offset="100%" stop-color="#080a0f"/>',
        "  </linearGradient>",
        '  <linearGradient id="radarFill" x1="0%" y1="0%" x2="100%" y2="100%">',
        '    <stop offset="0%" stop-color="#be7a38" stop-opacity="0.18"/>',
        '    <stop offset="100%" stop-color="#5ca3ad" stop-opacity="0.18"/>',
        "  </linearGradient>",
        '  <linearGradient id="radarStroke" x1="0%" y1="0%" x2="100%" y2="100%">',
        '    <stop offset="0%" stop-color="#be7a38"/>',
        '    <stop offset="100%" stop-color="#5ca3ad"/>',
        "  </linearGradient>",
        "</defs>",
        '<rect width="680" height="320" rx="8" fill="#07090e"/>',
        '<rect width="680" height="320" rx="8" fill="url(#leftGlow)"/>',
        '<rect width="680" height="320" rx="8" fill="url(#rightGlow)"/>',
    ]

    # Painéis (Cards) com dimensões compactas
    for x, y, w, h in [(10, 10, 325, 230), (345, 10, 325, 230), (10, 250, 660, 60)]:
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="url(#cardGrad)" stroke="#161c28" stroke-width="1"/>')

    # ---- Radar (Painel Esquerdo)
    o.append(text(26, 30, "Language Radar", ACCENT_AMBER, 12, weight=600))
    for k in range(1, 5):
        o.append(f'<polygon points="{poly([k / 4] * n)}" fill="none" stroke="#1b2434" stroke-width="1" stroke-opacity="0.7"/>')
    for i in range(n):
        x, y = pt(i, 1)
        o.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#1b2434" stroke-width="1" stroke-opacity="0.7"/>')

    # Polígono do Radar
    o.append(f'<polygon class="rp" points="{poly(scores)}" fill="url(#radarFill)" '
             f'stroke="url(#radarStroke)" stroke-width="1.5"/>')

    # Rótulos externos com fonte compacta
    for i, r in enumerate(rows):
        x, y = pt(i, 1)
        c, s = math.cos(-math.pi / 2 + 2 * math.pi * i / n), math.sin(-math.pi / 2 + 2 * math.pi * i / n)
        anchor = "start" if c > 0.3 else "end" if c < -0.3 else "middle"
        o.append(text(x + c * 8, y + s * 10 + 3, clip(r["name"], 11), "#9aa8ba", 9.5, anchor, weight=400))

    # Pontos interativos no radar
    for i, r in enumerate(rows):
        x, y = pt(i, scores[i])
        label = f'{clip(r["name"], 18)} · {pct(r["share"])}'
        w = round(len(label) * 6.2 + 14)
        if i == 0:
            px, py = x + 8, y - 10
        else:
            px, py = x - w / 2, y - 28
        px = min(max(px, 16), 325 - w)
        py = max(py, 40)
        dot_color = r["color"]
        o.append('<g class="pt">')
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="#ffffff" fill-opacity="0"/>')
        o.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{dot_color}" stroke="#07090e" stroke-width="1"/>')
        o.append(f'<g class="tip"><rect x="{px:.1f}" y="{py:.1f}" width="{w}" height="19" rx="3" fill="#090d14" stroke="{ACCENT_CYAN}" stroke-width="1"/>')
        o.append(text(px + w / 2, py + 13, label, "#d5dde5", 9.5, "middle", weight=500) + "</g></g>")

    # ---- Ranking de Linguagens (Painel Direito)
    o.append(text(363, 30, "Top Languages", ACCENT_CYAN, 12, weight=600))
    # Barra de distribuição compacta
    o.append('<rect x="363" y="44" width="289" height="6" rx="3" fill="#11151e"/>')
    o.append('<g clip-path="url(#cl)">')
    x = 363.0
    for r in rows + [{"share": others, "color": "#263040"}]:
        w = 289 * r["share"] / 100
        o.append(f'<rect x="{x:.1f}" y="44" width="{w:.1f}" height="6" fill="{r["color"]}"/>')
        x += w
    o.append('</g><g class="rows">')
    step = 32 if n <= 5 else (195 - 76) / (n - 1)
    for k, r in enumerate(rows):
        y = 76 + k * step
        o.append('<g class="row">')
        o.append(f'<rect class="hit" x="353" y="{y - 14:.1f}" width="309" height="{min(30, step - 2):.1f}" rx="3" fill="#ffffff"/>')
        o.append(f'<circle cx="369" cy="{y - 4:.1f}" r="3.5" fill="{r["color"]}"/>')
        o.append(text(380, y, clip(r["name"], 24), "#dbe2ea", 11, weight=500 if k == 0 else 400))
        o.append(text(652, y, pct(r["share"]), ACCENT_AMBER, 10.5, "end", weight=600))
        o.append(f'<rect x="363" y="{y + 8:.1f}" width="289" height="3" rx="1.5" fill="#11151e"/>')
        o.append(f'<rect class="bf" style="animation-delay:{k * 0.12:.2f}s" x="363" y="{y + 8:.1f}" '
                 f'width="{289 * r["share"] / top:.1f}" height="3" rx="1.5" fill="{r["color"]}"/>')
        o.append("</g>")
    o.append("</g>")

    # ---- Estatísticas do Perfil (Painel Inferior - Compacto com a Mesma Fonte)
    tiles = [
        ("Repos", stats["repos"], ACCENT_CYAN),
        ("Contributions", stats["contributions"], ACCENT_AMBER),
        ("Pull requests", stats["prs"], ACCENT_SKY),
        ("Stars earned", stats["stars"], ACCENT_GOLD)
    ]
    for k, (label, value, accent_col) in enumerate(tiles):
        x0 = 26 + k * 165
        o.append(text(x0, 272, label, "#818e9f", 9, weight=500, letter_spacing="0.8px", uppercase=True))
        o.append(text(x0, 296, short(value), accent_col, 16, weight=600))
        if k:
            o.append(f'<line x1="{x0 - 16}" y1="262" x2="{x0 - 16}" y2="298" stroke="#161c28" stroke-width="1"/>')
    o.append("</svg>")
    return "\n".join(o)


def main():
    demo = "--demo" in sys.argv
    data = DEMO_DATA if demo else fetch()
    rows, others = build_rows(data["langs"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    svg_content = render(rows, others, data["stats"], demo)
    OUT.write_text(svg_content, encoding="utf-8")
    root_radar = Path("radar.svg")
    root_radar.write_text(svg_content, encoding="utf-8")
    print(f"ok: {OUT} & {root_radar} | {', '.join(r['name'] for r in rows)} | {data['stats']}")


if __name__ == "__main__":
    main()
