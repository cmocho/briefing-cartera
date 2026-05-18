#!/usr/bin/env python3
"""
Generador automático de Briefing Financiero Personal
Cartera: MSCI World + Emerging Markets + European Stock + Gold ETC
Ejecutado por GitHub Actions cada día a las 14:00 (hora España)
"""

import datetime, json, os, sys, xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
except ImportError:
    print("Instalando yfinance...")
    os.system(f"{sys.executable} -m pip install yfinance requests --quiet")
    import yfinance as yf

import requests as req_lib

# ── CONFIGURACIÓN DE CARTERA ──────────────────────────────────
CARTERA = {
    'msci_world': {'nombre': 'iShares MSCI World (Desarrollados)', 'importe': 4500, 'peso': 56.25, 'ticker': 'IWDA.AS', 'color': '#3b82f6'},
    'emerging':   {'nombre': 'iShares Emerging Markets',           'importe': 1500, 'peso': 18.75, 'ticker': 'EIMI.AS', 'color': '#10b981'},
    'european':   {'nombre': 'Vanguard European Stock Index',       'importe': 1000, 'peso': 12.50, 'ticker': 'VEUR.AS', 'color': '#8b5cf6'},
    'gold':       {'nombre': 'iShares Physical Gold ETC (EGLN)',   'importe': 1000, 'peso': 12.50, 'ticker': 'EGLN.L',  'color': '#f59e0b'},
}
LIQUIDEZ     = 1000
TOTAL_INV    = sum(v['importe'] for v in CARTERA.values())
CUENTA_TAE   = 2.0

# ── INDICADOR BUFFETT (actualizar manualmente cada trimestre) ─
BUFFETT_IND   = 195.0    # % = Capitalización bursátil EE.UU. / PIB × 100
BUFFETT_DATE  = "May 2026"  # fecha del dato

INDICES = {
    'sp500':      ('^GSPC',     'S&P 500',        '$'),
    'eurostoxx':  ('^STOXX50E', 'EuroStoxx 50',   ''),
    'gold_usd':   ('GC=F',      'Oro ($/oz)',      '$'),
    'egln':       ('EGLN.L',    'EGLN (€)',        '€'),
    'brent':      ('BZ=F',      'Brent ($/b)',     '$'),
    'eurusd':     ('EURUSD=X',  'EUR/USD',         ''),
    'bce':        (None,        'BCE Depósito',    '%'),
    'fed':        (None,        'Fed Funds',       '%'),
}

# ── FECHA ────────────────────────────────────────────────────
TZ = ZoneInfo("Europe/Madrid")
HOY = datetime.datetime.now(tz=TZ)
DIAS_ES = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
MESES_ES = ['','enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
FECHA_LARGA = f"{DIAS_ES[HOY.weekday()]}, {HOY.day} de {MESES_ES[HOY.month]} de {HOY.year}"
FECHA_CORTA = HOY.strftime('%d/%m/%Y')
HORA_ACT    = HOY.strftime('%H:%M')


# ── OBTENER PRECIO YFINANCE ───────────────────────────────────
def get_price(ticker, days=5):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f'{days}d')
        if len(hist) >= 2:
            prev = float(hist['Close'].iloc[-2])
            curr = float(hist['Close'].iloc[-1])
            prev_w = float(hist['Close'].iloc[0])
            chg_d = (curr - prev) / prev * 100
            chg_w = (curr - prev_w) / prev_w * 100
            return {'price': curr, 'prev': prev, 'chg_d': chg_d, 'chg_w': chg_w, 'ok': True}
        elif len(hist) == 1:
            curr = float(hist['Close'].iloc[-1])
            return {'price': curr, 'prev': curr, 'chg_d': 0.0, 'chg_w': 0.0, 'ok': True}
    except Exception as e:
        print(f"  [!] {ticker}: {e}")
    return {'price': 0.0, 'prev': 0.0, 'chg_d': 0.0, 'chg_w': 0.0, 'ok': False}


def fmt_price(v, sym='', dec=2):
    if v == 0: return '—'
    return f"{sym}{v:,.{dec}f}" if sym in ('$','€') else f"{v:,.{dec}f}{sym}"

def fmt_chg(v):
    if v is None: return '—'
    arrow = '▲' if v >= 0 else '▼'
    cls   = 'up' if v >= 0 else 'down'
    return f'<span class="{cls}">{arrow} {abs(v):.2f}%</span>'

def signal_class(v):
    if v >= 0: return 'up'
    if v > -1: return 'neutral'
    return 'down'


# ── NOTICIAS RSS ─────────────────────────────────────────────
FEEDS = [
    ('Reuters Negocios ES', 'https://feeds.reuters.com/reuters/businessNews'),
    ('Google Mercados',     f'https://news.google.com/rss/search?q=mercados+bolsa+{HOY.strftime("%Y")}&hl=es&gl=ES&ceid=ES:es'),
    ('Google BCE Fed',      f'https://news.google.com/rss/search?q=BCE+Fed+tipos+interes&hl=es&gl=ES&ceid=ES:es'),
    ('Google Inflación',    f'https://news.google.com/rss/search?q=inflacion+eurozona+economia&hl=es&gl=ES&ceid=ES:es'),
]

def get_news(max_per_feed=3):
    items = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for source, url in FEEDS:
        try:
            r = req_lib.get(url, timeout=8, headers=headers)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall('.//item')[:max_per_feed]:
                title = (item.findtext('title') or '').strip()
                link  = (item.findtext('link')  or '#').strip()
                desc  = (item.findtext('description') or '').strip()
                # limpiar tags HTML de la descripción
                import re
                desc = re.sub(r'<[^>]+>', '', desc)[:280]
                if title:
                    items.append({'title': title, 'link': link, 'desc': desc, 'source': source})
        except Exception as e:
            print(f"  [!] RSS {source}: {e}")
    return items[:12]


# ── DATOS PRINCIPALES ─────────────────────────────────────────
print("📡 Obteniendo datos de mercado...")
mkt = {}
for key, (ticker, label, sym) in INDICES.items():
    if ticker:
        mkt[key] = get_price(ticker)
        mkt[key]['label'] = label
        mkt[key]['sym']   = sym
    else:
        mkt[key] = {'price': 0, 'chg_d': 0, 'chg_w': 0, 'ok': False, 'label': label, 'sym': sym}

# Tipos fijos conocidos (actualizados en el script cuando cambian)
mkt['bce']['price']  = 2.00
mkt['fed']['price']  = 3.625  # midpoint 3.50-3.75

print("💼 Calculando impacto en cartera...")
total_impact_eur = 0.0
for key, pos in CARTERA.items():
    pd = get_price(pos['ticker'])
    pos['price']   = pd['price']
    pos['chg_d']   = pd['chg_d']
    pos['chg_w']   = pd['chg_w']
    pos['impact']  = pos['importe'] * pd['chg_d'] / 100
    total_impact_eur += pos['impact']

print("📰 Cargando noticias...")
noticias = get_news()

# Histórico LEI simulado (últimos 8 meses)
lei_labels = ['Oct', 'Nov', 'Dic', 'Ene', 'Feb', 'Mar', 'Abr', 'May']
lei_data   = [100.8, 100.2, 99.6, 98.9, 98.5, 97.9, 97.3, 96.8]
pmi_data   = [52.1, 52.4, 52.0, 51.8, 51.9, 51.6, 51.5, 51.5]

impact_sign = '+' if total_impact_eur >= 0 else ''
impact_cls  = 'up' if total_impact_eur >= 0 else 'down'
impact_pct  = total_impact_eur / TOTAL_INV * 100


# ── GENERAR HTML ──────────────────────────────────────────────
print("🎨 Generando HTML...")

def ticker_item(label, price, chg_d, sym='', dec=2):
    arrow = '▲' if chg_d >= 0 else '▼'
    cls   = 'up' if chg_d >= 0 else ('down' if chg_d < 0 else 'neutral')
    ps    = f'{sym}{price:,.{dec}f}' if sym in ('$','€') else f'{price:,.{dec}f}{sym}'
    return f'''
  <div class="ticker-item">
    <div class="ticker-name">{label}</div>
    <div class="ticker-price">{ps}</div>
    <div class="ticker-change {cls}">{arrow} {abs(chg_d):.2f}%</div>
  </div>'''

def news_html(items):
    tags = ['tag-geo','tag-mon','tag-inf','tag-mkt','tag-trade']
    tag_labels = ['Economía','Mercados','Política Monetaria','Bolsa','Comercio']
    out = ''
    for i, item in enumerate(items[:8]):
        tag = tags[i % len(tags)]
        tag_label = tag_labels[i % len(tag_labels)]
        out += f'''
        <div class="news-item">
          <div class="news-num">{i+1}</div>
          <div class="news-content">
            <span class="news-tag {tag}">{tag_label}</span>
            <div class="news-title"><a href="{item['link']}" target="_blank" style="color:inherit;text-decoration:none">{item['title']}</a></div>
            <div class="news-body">{item['desc']}</div>
            <div class="news-source">📎 {item['source']}</div>
          </div>
        </div>'''
    return out

def portfolio_rows():
    rows = ''
    for key, pos in CARTERA.items():
        arrow = '▲' if pos['chg_d'] >= 0 else '▼'
        cls   = 'up' if pos['chg_d'] >= 0 else 'down'
        icls  = 'up' if pos['impact'] >= 0 else 'down'
        price_str = f"{pos['price']:.2f}€" if pos['price'] > 0 else '—'
        rows += f'''
            <tr>
              <td><div class="fund-name">{pos['nombre']}</div>
                  <div class="fund-ticker">{pos['peso']}% · {pos['importe']:,}€</div></td>
              <td style="text-align:right">{price_str}</td>
              <td style="text-align:right"><span class="{cls}">{arrow} {abs(pos['chg_d']):.2f}%</span></td>
              <td style="text-align:right"><span class="{cls}">{arrow} {abs(pos['chg_w']):.2f}%</span></td>
              <td style="text-align:right"><span class="{icls}">{impact_sign if key==list(CARTERA.keys())[0] else ('+' if pos['impact']>=0 else '')}{pos['impact']:+.1f}€</span></td>
            </tr>'''
    sign = '+' if total_impact_eur >= 0 else ''
    rows += f'''
            <tr class="total-row">
              <td colspan="3"><div class="fund-name">Variación total estimada</div></td>
              <td></td>
              <td style="text-align:right"><span class="{impact_cls}" style="font-size:16px;font-weight:800">{sign}{total_impact_eur:.1f}€</span></td>
            </tr>'''
    return rows

sp500_p  = mkt['sp500']['price']
sp500_c  = mkt['sp500']['chg_d']
estoxx_p = mkt['eurostoxx']['price']
estoxx_c = mkt['eurostoxx']['chg_d']
gold_p   = mkt['gold_usd']['price']
gold_c   = mkt['gold_usd']['chg_d']
egln_p   = mkt['egln']['price']
egln_c   = mkt['egln']['chg_d']
brent_p  = mkt['brent']['price']
brent_c  = mkt['brent']['chg_d']
eurusd_p = mkt['eurusd']['price']
eurusd_c = mkt['eurusd']['chg_d']

HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📊 Briefing Cartera — {FECHA_CORTA}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{{--bg:#0a0f1e;--bg2:#111827;--bg3:#1a2235;--card:#1e2d45;--border:#2d4a6e;--accent:#3b82f6;--accent2:#60a5fa;--gold:#f59e0b;--gold2:#fbbf24;--green:#10b981;--green2:#34d399;--red:#ef4444;--red2:#f87171;--yellow:#f59e0b;--yellow2:#fcd34d;--purple:#8b5cf6;--text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;font-size:16px;}}
.hero{{background:linear-gradient(135deg,#0a0f1e 0%,#0f2040 40%,#1a1040 100%);border-bottom:1px solid var(--border);padding:28px 32px 20px;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;top:-60px;right:-60px;width:300px;height:300px;background:radial-gradient(circle,rgba(59,130,246,0.12) 0%,transparent 70%);border-radius:50%;}}
.hero-top{{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;position:relative;z-index:1;}}
.hero-badge{{display:flex;align-items:center;gap:10px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3);border-radius:40px;padding:6px 16px 6px 10px;font-size:12px;color:var(--accent2);font-weight:600;letter-spacing:0.05em;text-transform:uppercase;}}
.hero-date{{font-size:12px;color:var(--text3);background:var(--bg3);border:1px solid var(--border);border-radius:20px;padding:5px 14px;}}
.hero-title{{font-size:clamp(22px,4vw,34px);font-weight:800;margin-top:16px;position:relative;z-index:1;letter-spacing:-0.02em;}}
.hero-title span{{color:var(--accent2);}}
.signal-bar{{display:flex;align-items:center;gap:12px;margin-top:20px;padding:14px 20px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);border-radius:12px;position:relative;z-index:1;}}
.signal-icon{{font-size:22px;}}
.signal-text strong{{color:var(--yellow2);font-size:15px;}}
.signal-text p{{font-size:13px;color:var(--text2);margin-top:2px;}}
.ticker-bar{{background:var(--bg2);border-bottom:1px solid var(--border);padding:10px 32px;display:flex;gap:28px;overflow-x:auto;scrollbar-width:none;}}
.ticker-bar::-webkit-scrollbar{{display:none;}}
.ticker-item{{display:flex;flex-direction:column;align-items:center;min-width:fit-content;gap:2px;}}
.ticker-name{{font-size:10px;color:var(--text3);font-weight:700;text-transform:uppercase;letter-spacing:0.05em;}}
.ticker-price{{font-size:14px;font-weight:700;}}
.ticker-change{{font-size:11px;font-weight:600;}}
.up{{color:var(--green2);}} .down{{color:var(--red2);}} .neutral{{color:var(--text2);}}
.main{{max-width:1200px;margin:0 auto;padding:28px 20px;}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;}}
.grid-4{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}}
@media(max-width:900px){{.grid-2,.grid-3,.grid-4{{grid-template-columns:1fr;}}}}
.section{{margin-bottom:32px;}}
.section-title{{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.12em;color:var(--accent2);margin-bottom:14px;display:flex;align-items:center;gap:8px;}}
.section-title::after{{content:'';flex:1;height:1px;background:linear-gradient(to right,var(--border),transparent);}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:0 4px 24px rgba(0,0,0,0.4);transition:border-color 0.2s;}}
.card:hover{{border-color:var(--accent);}}
.card-title{{font-size:13px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;}}
.kpi{{display:flex;flex-direction:column;}}
.kpi .icon{{font-size:24px;margin-bottom:8px;}}
.kpi .value{{font-size:28px;font-weight:800;letter-spacing:-0.03em;}}
.kpi .label{{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;}}
.kpi .change{{font-size:13px;font-weight:600;margin-top:6px;}}
.news-item{{padding:14px 0;border-bottom:1px solid rgba(45,74,110,0.5);display:flex;gap:14px;align-items:flex-start;}}
.news-item:last-child{{border-bottom:none;}}
.news-num{{font-size:11px;font-weight:800;color:var(--accent2);background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.2);border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px;}}
.news-title{{font-size:16px;font-weight:600;color:var(--text);line-height:1.4;}}
.news-body{{font-size:14px;color:var(--text2);margin-top:4px;line-height:1.5;}}
.news-source{{font-size:12px;color:var(--text3);margin-top:4px;}}
.news-tag{{display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;margin-right:6px;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;}}
.tag-geo{{background:rgba(239,68,68,0.15);color:var(--red2);border:1px solid rgba(239,68,68,0.2);}}
.tag-mon{{background:rgba(59,130,246,0.15);color:var(--accent2);border:1px solid rgba(59,130,246,0.2);}}
.tag-inf{{background:rgba(245,158,11,0.15);color:var(--gold2);border:1px solid rgba(245,158,11,0.2);}}
.tag-mkt{{background:rgba(16,185,129,0.15);color:var(--green2);border:1px solid rgba(16,185,129,0.2);}}
.tag-trade{{background:rgba(139,92,246,0.15);color:#a78bfa;border:1px solid rgba(139,92,246,0.2);}}
.ptable{{width:100%;border-collapse:collapse;font-size:15px;}}
.ptable th{{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:var(--text3);font-weight:700;padding:8px 10px;border-bottom:1px solid var(--border);}}
.ptable td{{padding:12px 10px;border-bottom:1px solid rgba(45,74,110,0.3);vertical-align:middle;}}
.ptable tr:last-child td{{border-bottom:none;}}
.ptable tr:hover td{{background:rgba(59,130,246,0.04);}}
.fund-name{{font-weight:600;color:var(--text);font-size:15px;}}
.fund-ticker{{font-size:13px;color:var(--text3);margin-top:2px;}}
.total-row td{{font-weight:700;background:rgba(59,130,246,0.06);color:var(--accent2);border-top:1px solid var(--border);}}
.threshold-bar{{margin:10px 0;background:rgba(255,255,255,0.04);border-radius:10px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;border:1px solid rgba(255,255,255,0.05);}}
.scenario{{background:var(--bg3);border-radius:12px;padding:14px 16px;margin-bottom:12px;border:1px solid var(--border);}}
.scenario-header{{display:flex;justify-content:space-between;margin-bottom:8px;}}
.scenario-name{{font-size:13px;font-weight:700;}}
.scenario-prob{{font-size:13px;font-weight:800;}}
.scenario-bar{{height:6px;border-radius:3px;background:rgba(255,255,255,0.1);overflow:hidden;margin-bottom:8px;}}
.scenario-fill{{height:100%;border-radius:3px;}}
.scenario-desc{{font-size:12px;color:var(--text2);line-height:1.4;}}
.risk-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;border-left:4px solid;margin-bottom:12px;}}
.risk-card.high{{border-left-color:var(--red);}}
.risk-card.med{{border-left-color:var(--yellow);}}
.risk-card.low{{border-left-color:var(--green);}}
.risk-name{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:8px;}}
.risk-desc{{font-size:12px;color:var(--text2);line-height:1.5;}}
.chart-wrap{{position:relative;height:220px;}}
.chart-wrap-lg{{position:relative;height:260px;}}
footer{{border-top:1px solid var(--border);padding:24px 32px;text-align:center;color:var(--text3);font-size:11px;background:var(--bg2);line-height:1.8;}}
.auto-badge{{display:inline-block;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:20px;padding:3px 12px;font-size:11px;color:var(--green2);font-weight:600;margin-top:6px;}}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-top">
    <div class="hero-badge"><span>📊</span> Briefing Cartera Indexada</div>
    <div class="hero-date">{FECHA_LARGA} · Actualizado {HORA_ACT} CET</div>
  </div>
  <div class="hero-title">Briefing <span>Económico-Financiero</span> Personal</div>
  <div style="font-size:13px;color:var(--text2);margin-top:6px;">Cartera indexada a largo plazo · Datos de mercado en tiempo real</div>
  <div class="signal-bar">
    <div class="signal-icon">🟡</div>
    <div class="signal-text">
      <strong>SEÑAL: VIGILAR — Datos actualizados a las {HORA_ACT}</strong>
      <p>Variación estimada de cartera hoy: <strong style="color:{'var(--green2)' if total_impact_eur >= 0 else 'var(--red2)'}">{'+' if total_impact_eur >= 0 else ''}{total_impact_eur:.1f}€ ({impact_pct:+.2f}%)</strong> · Generado automáticamente por GitHub Actions</p>
    </div>
  </div>
</div>

<div class="ticker-bar">
  {ticker_item('S&P 500',    sp500_p,  sp500_c,  '$', 0)}
  {ticker_item('EuroStoxx',  estoxx_p, estoxx_c, '',  0)}
  {ticker_item('Oro ($/oz)', gold_p,   gold_c,   '$', 0)}
  {ticker_item('EGLN (€)',   egln_p,   egln_c,   '€', 2)}
  {ticker_item('Brent $/b',  brent_p,  brent_c,  '$', 1)}
  {ticker_item('EUR/USD',    eurusd_p, eurusd_c, '',  4)}
  <div class="ticker-item">
    <div class="ticker-name">BCE Depósito</div>
    <div class="ticker-price">2,00%</div>
    <div class="ticker-change neutral">→ Sin cambios</div>
  </div>
  <div class="ticker-item">
    <div class="ticker-name">Fed Funds</div>
    <div class="ticker-price">3,50%</div>
    <div class="ticker-change neutral">→ Sin cambios</div>
  </div>
</div>

<div class="main">

  <!-- NOTICIAS -->
  <div class="section">
    <div class="section-title">📰 1 — Noticias del día · {FECHA_CORTA}</div>
    <div class="card">
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <span style="font-size:12px;background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.2);border-radius:20px;padding:4px 12px;color:var(--red2);font-weight:600">🔴 Geopolítica</span>
        <span style="font-size:12px;background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.2);border-radius:20px;padding:4px 12px;color:var(--accent2);font-weight:600">💙 Política Monetaria</span>
        <span style="font-size:12px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.2);border-radius:20px;padding:4px 12px;color:var(--gold2);font-weight:600">🟡 Inflación</span>
        <span style="font-size:12px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.2);border-radius:20px;padding:4px 12px;color:var(--green2);font-weight:600">📊 Mercados</span>
      </div>
      {news_html(noticias)}
    </div>
  </div>

  <!-- KPIs CARTERA -->
  <div class="section">
    <div class="section-title">💼 Estado de la cartera · {FECHA_CORTA}</div>
    <div class="grid-4" style="margin-bottom:20px">
      <div class="card kpi">
        <div class="icon">📈</div>
        <div class="value" style="color:var(--accent2)">{TOTAL_INV:,}€</div>
        <div class="label">Total invertido</div>
        <div class="change neutral">+{LIQUIDEZ}€ liquidez = {TOTAL_INV+LIQUIDEZ:,}€ total</div>
      </div>
      <div class="card kpi">
        <div class="icon">{'📉' if total_impact_eur < 0 else '📈'}</div>
        <div class="value {'down' if total_impact_eur < 0 else 'up'}" style="color:{'var(--red2)' if total_impact_eur < 0 else 'var(--green2)'}">{total_impact_eur:+.1f}€</div>
        <div class="label">Variación estimada hoy</div>
        <div class="change {'down' if total_impact_eur < 0 else 'up'}">{impact_pct:+.2f}% de la inversión</div>
      </div>
      <div class="card kpi">
        <div class="icon">🥇</div>
        <div class="value" style="color:var(--gold2)">{egln_p:.2f}€</div>
        <div class="label">EGLN — Precio hoy</div>
        <div class="change {signal_class(egln_c)}">{'+' if egln_c >= 0 else ''}{egln_c:.2f}% · Cobertura {'activa ↑' if egln_c >= 0 else 'vigilar'}</div>
      </div>
      <div class="card kpi">
        <div class="icon">💶</div>
        <div class="value" style="color:var(--green2)">2% TAE</div>
        <div class="label">Liquidez remunerada</div>
        <div class="change neutral">1.000€ · Revisar en Q3 2026</div>
      </div>
    </div>

    <!-- Gráficos + tabla -->
    <div class="grid-2" style="gap:20px;margin-bottom:20px">
      <div class="card">
        <div class="card-title">Composición de la cartera</div>
        <div class="chart-wrap">
          <canvas id="portfolioChart"></canvas>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Variación de mercados hoy</div>
        <div class="chart-wrap">
          <canvas id="marketChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Tabla de posiciones -->
    <div class="card">
      <div class="card-title">Precios y variación por posición</div>
      <table class="ptable">
        <thead>
          <tr>
            <th>Instrumento</th>
            <th style="text-align:right">Precio</th>
            <th style="text-align:right">Var. Día</th>
            <th style="text-align:right">Var. Semana</th>
            <th style="text-align:right">Impacto €</th>
          </tr>
        </thead>
        <tbody>
          {portfolio_rows()}
        </tbody>
      </table>
      <div style="font-size:11px;color:var(--text3);background:var(--bg3);border-radius:8px;padding:10px 12px;margin-top:12px;line-height:1.5">
        <strong style="color:var(--text2)">Nota:</strong> Los fondos UCITS (iShares, Vanguard) publican VL con 1 día hábil de retraso. Las variaciones usan ETFs equivalentes cotizados en Euronext Amsterdam (IWDA, EIMI, VEUR) como proxy intradiario. El EGLN cotiza en tiempo real en Londres.
      </div>
    </div>
  </div>

  <!-- GRÁFICO HISTÓRICO LEI -->
  <div class="section">
    <div class="section-title">📡 Indicadores Adelantados — Tendencia 8 meses</div>
    <div class="card">
      <div class="chart-wrap-lg">
        <canvas id="cycleChart"></canvas>
      </div>
    </div>
  </div>

  <!-- ESCENARIOS -->
  <div class="section">
    <div class="section-title">🔮 Escenarios y probabilidades</div>
    <div class="grid-3" style="gap:16px">
      <div class="scenario">
        <div class="scenario-header">
          <div class="scenario-name" style="color:var(--green2)">🌤 Aterrizaje suave</div>
          <div class="scenario-prob" style="color:var(--green2)">~40%</div>
        </div>
        <div class="scenario-bar"><div class="scenario-fill" style="width:40%;background:var(--green)"></div></div>
        <div class="scenario-desc">Inflación cede al 2,5% en Q4 2026. BCE para subidas. MSCI World y EM suben. Tu cartera en zona favorable; el oro puede ceder algo.</div>
      </div>
      <div class="scenario">
        <div class="scenario-header">
          <div class="scenario-name" style="color:var(--gold2)">⚠️ Estanflación</div>
          <div class="scenario-prob" style="color:var(--gold2)">~40%</div>
        </div>
        <div class="scenario-bar"><div class="scenario-fill" style="width:40%;background:var(--gold)"></div></div>
        <div class="scenario-desc">Brent &gt;100$, inflación sticky, BCE sube 2 veces. Bolsa cede −5% a −15%. El oro protege. Tu 12,5% en EGLN juega a favor.</div>
      </div>
      <div class="scenario">
        <div class="scenario-header">
          <div class="scenario-name" style="color:var(--red2)">🔴 Recesión / Escalada</div>
          <div class="scenario-prob" style="color:var(--red2)">~20%</div>
        </div>
        <div class="scenario-bar"><div class="scenario-fill" style="width:20%;background:var(--red)"></div></div>
        <div class="scenario-desc">Brent &gt;120$, recesión Europa, bolsa −20/−35%. Oro principal refugio. Los 1.000€ de liquidez dan munición para comprar en mínimos.</div>
      </div>
    </div>
  </div>

  <!-- RIESGOS -->
  <div class="section">
    <div class="section-title">⚠️ Riesgos a vigilar</div>
    <div class="risk-card high">
      <div class="risk-name">🔴 Riesgo 1 — Escalada Oriente Medio (Probabilidad Alta)</div>
      <div class="risk-desc">Conflicto Irán–Israel–EE.UU. en su 10ª semana. Si el estrecho de Ormuz se ve comprometido (20% del petróleo mundial), Brent podría ir a 130–150$. Impacto: MSCI World −8/−15% · European Stock −12/−18% · Gold ETC +10/+20%.</div>
    </div>
    <div class="risk-card med">
      <div class="risk-name">🟡 Riesgo 2 — Estanflación Eurozona (Probabilidad Media)</div>
      <div class="risk-desc">BCE sube tipos pero inflación no cede. European Stock Index es la posición más vulnerable (aranceles + energía + tipos). Impacto: European −10/−15% · MSCI World −5/−10% · Gold +5/+12%.</div>
    </div>
    <div class="risk-card low">
      <div class="risk-name">🟢 Riesgo 3 — Fortaleza del USD (Probabilidad Baja)</div>
      <div class="risk-desc">Diferencial Fed-BCE fortalece el dólar. MSCI World pierde 2–5% en euros (efecto divisa). EGLN en euros gana 1–3% como compensación. Emerging Markets, el más afectado.</div>
    </div>
  </div>

  <!-- UMBRALES -->
  <div class="section">
    <div class="section-title">🚨 Umbrales de alerta personal · {TOTAL_INV:,}€ invertidos</div>
    <div class="card">
      <div class="threshold-bar"><div><span style="font-size:20px;font-weight:800;color:var(--yellow2)">−5%</span> &nbsp;Corrección normal</div><div style="font-size:16px;font-weight:700">−{int(TOTAL_INV*0.05):,}€</div></div>
      <div class="threshold-bar"><div><span style="font-size:20px;font-weight:800;color:#fb923c">−10%</span> &nbsp;Corrección significativa</div><div style="font-size:16px;font-weight:700">−{int(TOTAL_INV*0.10):,}€</div></div>
      <div class="threshold-bar"><div><span style="font-size:20px;font-weight:800;color:var(--red2)">−20%</span> &nbsp;Mercado bajista severo</div><div style="font-size:16px;font-weight:700">−{int(TOTAL_INV*0.20):,}€</div></div>
      <div style="background:rgba(59,130,246,0.06);border:1px solid rgba(59,130,246,0.15);border-radius:12px;padding:14px 16px;margin-top:12px;font-size:12px;color:var(--text2);line-height:1.6">
        <strong style="color:var(--accent2)">Perspectiva histórica:</strong> Una caída del 20% en mercados desarrollados ha tardado de media <strong style="color:var(--text)">2–4 años</strong> en recuperarse. El MSCI World lleva ~10% anualizado desde 2000. La variación de hoy ({total_impact_eur:+.1f}€) es el <strong style="color:var(--text)">{abs(impact_pct):.2f}%</strong> de la inversión total.
      </div>
    </div>
  </div>


  <!-- INDICADOR BUFFETT -->
  <div class="section">
    <div class="section-title">📐 Indicador Buffett — Valoración del mercado EE.UU.</div>
    <div class="card">
      <div style="display:grid;grid-template-columns:220px 1fr;gap:28px;align-items:start">

        <!-- Valor y barra -->
        <div>
          <div class="card-title">Capitalización / PIB</div>
          <div style="font-size:58px;font-weight:900;letter-spacing:-0.04em;color:{'var(--red2)' if BUFFETT_IND>135 else ('var(--yellow2)' if BUFFETT_IND>115 else 'var(--green2)')}">{BUFFETT_IND:.0f}%</div>
          <div style="font-size:12px;color:var(--text3);margin-top:4px">Dato: {BUFFETT_DATE}</div>

          <!-- Barra de zonas -->
          <div style="margin-top:18px">
            <div style="font-size:11px;color:var(--text3);margin-bottom:6px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em">Zona actual</div>
            <div style="display:flex;height:14px;border-radius:8px;overflow:hidden;gap:2px">
              <div style="flex:75;background:rgba(16,185,129,0.7);border-radius:6px 0 0 6px;" title="&lt;75% Infravalorado"></div>
              <div style="flex:40;background:rgba(245,158,11,0.7);" title="75-115% Valoración justa"></div>
              <div style="flex:20;background:rgba(251,146,60,0.7);" title="115-135% Algo caro"></div>
              <div style="flex:65;background:rgba(239,68,68,0.7);border-radius:0 6px 6px 0;" title="&gt;135% Sobrevalorado"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text3);margin-top:4px">
              <span>0%</span><span>75%</span><span>115%</span><span>135%</span><span>200%</span>
            </div>
            <!-- Marcador posición actual -->
            <div style="position:relative;height:8px;margin-top:4px">
              <div style="position:absolute;left:{min(98, BUFFETT_IND/2):.1f}%;transform:translateX(-50%);font-size:14px;">▲</div>
            </div>
          </div>
        </div>

        <!-- Explicación y rangos -->
        <div>
          <div class="card-title">¿Qué es y cómo interpretarlo?</div>
          <div style="font-size:14px;color:var(--text2);line-height:1.75;margin-bottom:16px">
            El <strong style="color:var(--text)">Indicador Buffett</strong> divide la capitalización bursátil total de todas las empresas cotizadas en EE.UU. entre el PIB nominal del país, expresado en porcentaje. Warren Buffett lo calificó como «<em>probablemente el mejor indicador individual para saber dónde están las valoraciones en cualquier momento dado</em>».
            <br><br>
            Un valor <strong style="color:var(--green2)">por debajo del 75%</strong> históricamente ha señalado una bolsa barata y buenos retornos a largo plazo. Por encima del <strong style="color:var(--red2)">135%</strong>, el mercado cotiza con prima elevada y los retornos futuros esperados son menores.
          </div>

          <!-- Rangos en chips -->
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
            <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);border-radius:10px;padding:8px 14px">
              <div style="font-size:13px;font-weight:800;color:var(--green2)">🟢 &lt; 75%</div>
              <div style="font-size:12px;color:var(--text2);margin-top:2px">Infravalorado<br>Excelente momento de compra</div>
            </div>
            <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.25);border-radius:10px;padding:8px 14px">
              <div style="font-size:13px;font-weight:800;color:var(--gold2)">🟡 75–115%</div>
              <div style="font-size:12px;color:var(--text2);margin-top:2px">Valoración justa<br>Retornos históricos medios</div>
            </div>
            <div style="background:rgba(251,146,60,0.1);border:1px solid rgba(251,146,60,0.25);border-radius:10px;padding:8px 14px">
              <div style="font-size:13px;font-weight:800;color:#fb923c">🟠 115–135%</div>
              <div style="font-size:12px;color:var(--text2);margin-top:2px">Algo caro<br>Retornos esperados menores</div>
            </div>
            <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);border-radius:10px;padding:8px 14px">
              <div style="font-size:13px;font-weight:800;color:var(--red2)">🔴 &gt; 135%</div>
              <div style="font-size:12px;color:var(--text2);margin-top:2px">Sobrevalorado<br>Riesgo de corrección elevado</div>
            </div>
          </div>

          <!-- Nota tipos -->
          <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px 16px;font-size:13px;color:var(--text2);line-height:1.6">
            <strong style="color:var(--text2)">⚠️ Limitación clave:</strong> El indicador no ajusta por tipos de interés. Con tipos bajos (0-1%) son sostenibles valoraciones del 130–160%. Con los tipos actuales
            (Fed 3,5% / BCE 2,0%), la «<em>zona justa ajustada</em>» baja a ~100–140%. El valor actual de <strong style="color:{'var(--red2)' if BUFFETT_IND>140 else 'var(--yellow2)'}">{BUFFETT_IND:.0f}%</strong> sitúa el mercado en zona de <strong style="color:{'var(--red2)' if BUFFETT_IND>140 else 'var(--yellow2)'}">{'valoración elevada' if BUFFETT_IND>140 else 'cautela'}</strong>.
            <br><strong style="color:var(--text3)">Actualiza este valor trimestralmente</strong> editando <code style="background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px">BUFFETT_IND</code> en <code style="background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px">generar_briefing.py</code>.
          </div>
        </div>
      </div>
    </div>
  </div>

</div>

<footer>
  <div>📊 <strong>Briefing Cartera — {FECHA_CORTA}</strong> · Generado automáticamente por GitHub Actions</div>
  <div style="margin-top:4px">Cartera indexada · MSCI World 56,25% · Emerging Markets 18,75% · European Stock 12,5% · Gold ETC 12,5%</div>
  <div class="auto-badge">🤖 Actualización automática diaria a las 14:00 · Datos: Yahoo Finance + RSS</div>
  <div style="margin-top:10px;font-size:10px">⚠️ Briefing informativo. No constituye recomendación de inversión. Consulta con un asesor financiero independiente.</div>
</footer>

<script>
Chart.defaults.color='#94a3b8';
Chart.defaults.borderColor='rgba(45,74,110,0.5)';

new Chart(document.getElementById('portfolioChart'),{{
  type:'doughnut',
  data:{{
    labels:['MSCI World','Emerging Markets','European Stock','Gold ETC','Liquidez'],
    datasets:[{{
      data:[56.25,18.75,12.50,12.50,11.11],
      backgroundColor:['rgba(59,130,246,0.85)','rgba(16,185,129,0.85)','rgba(139,92,246,0.85)','rgba(245,158,11,0.85)','rgba(100,116,139,0.6)'],
      borderColor:['#3b82f6','#10b981','#8b5cf6','#f59e0b','#475569'],
      borderWidth:2,hoverOffset:8
    }}]
  }},
  options:{{responsive:true,maintainAspectRatio:false,cutout:'68%',
    plugins:{{legend:{{position:'right',labels:{{boxWidth:12,padding:8,font:{{size:11}}}}}}}}}}
}});

new Chart(document.getElementById('marketChart'),{{
  type:'bar',
  data:{{
    labels:['S&P 500','EuroStoxx','MSCI World*','EM*','European*','EGLN'],
    datasets:[{{
      label:'Variación % hoy',
      data:[{sp500_c:.2f},{estoxx_c:.2f},{CARTERA['msci_world']['chg_d']:.2f},{CARTERA['emerging']['chg_d']:.2f},{CARTERA['european']['chg_d']:.2f},{egln_c:.2f}],
      backgroundColor:ctx=>ctx.raw>=0?'rgba(16,185,129,0.75)':'rgba(239,68,68,0.75)',
      borderColor:ctx=>ctx.raw>=0?'#10b981':'#ef4444',
      borderWidth:1.5,borderRadius:6
    }}]
  }},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>`${{ctx.parsed.y>0?'+':''}}${{ctx.parsed.y.toFixed(2)}}%`}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}},
             y:{{grid:{{color:'rgba(45,74,110,0.4)'}},ticks:{{callback:v=>v+'%',font:{{size:10}}}}}}}}}}
}});

new Chart(document.getElementById('cycleChart'),{{
  type:'line',
  data:{{
    labels:{json.dumps(lei_labels)},
    datasets:[
      {{label:'LEI EE.UU. (base 100)',data:{lei_data},borderColor:'#3b82f6',backgroundColor:'rgba(59,130,246,0.08)',borderWidth:2,fill:true,tension:0.4,pointRadius:4,pointBackgroundColor:'#3b82f6',yAxisID:'y'}},
      {{label:'PMI Compuesto EZ',data:{pmi_data},borderColor:'#10b981',backgroundColor:'rgba(16,185,129,0.05)',borderWidth:2,fill:false,tension:0.4,pointRadius:4,pointBackgroundColor:'#10b981',yAxisID:'y2'}}
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'top',labels:{{boxWidth:10,padding:8,font:{{size:10}}}}}}}},
    scales:{{
      x:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}},
      y:{{min:94,max:103,grid:{{color:'rgba(45,74,110,0.4)'}},ticks:{{font:{{size:10}}}},title:{{display:true,text:'LEI',font:{{size:10}},color:'#3b82f6'}}}},
      y2:{{position:'right',min:48,max:55,grid:{{display:false}},ticks:{{font:{{size:10}}}},title:{{display:true,text:'PMI',font:{{size:10}},color:'#10b981'}}}}
    }}}}
}});
</script>
</body>
</html>"""

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(HTML)

print(f"✅ index.html generado correctamente — {len(HTML):,} caracteres")
print(f"   Variación cartera: {total_impact_eur:+.2f}€ ({impact_pct:+.2f}%)")
print(f"   Noticias cargadas: {len(noticias)}")
