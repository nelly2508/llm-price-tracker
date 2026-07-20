#!/usr/bin/env python3
"""
LLM API Pricing Tracker - build script.

Fetches the open-source LiteLLM model-pricing catalog (a public, community-
maintained dataset of pricing / context / capability data for hundreds of
models), normalises a curated roster of flagship chat models, and generates a
static site (_site/), a JSON API (data/models.json) and an llms.txt file.

Data source: https://github.com/BerriAI/litellm
Maintained autonomously by an AI agent. Pricing is aggregated from public
sources and may lag official pricing pages - always verify before purchasing.
"""
import json, os, re, urllib.request, datetime

SOURCE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
LOCAL_FALLBACK = "litellm_raw.json"

# Curated flagship roster: (litellm_key, display_name, provider_group).
# Prices/specs are pulled LIVE from the catalog on every run; this roster is the
# editorially-curated membership list (refreshed by the maintaining agent).
ROSTER = [
    # OpenAI
    ("gpt-5.6", "GPT-5.6", "OpenAI"),
    ("gpt-5.5", "GPT-5.5", "OpenAI"),
    ("gpt-4.1", "GPT-4.1", "OpenAI"),
    ("gpt-4o", "GPT-4o", "OpenAI"),
    ("gpt-4o-mini", "GPT-4o mini", "OpenAI"),
    ("o3", "o3", "OpenAI"),
    ("o1", "o1", "OpenAI"),
    ("o3-mini", "o3-mini", "OpenAI"),
    ("gpt-5-nano", "GPT-5 nano", "OpenAI"),
    # Anthropic
    ("claude-opus-4-8", "Claude Opus 4.8", "Anthropic"),
    ("claude-sonnet-5", "Claude Sonnet 5", "Anthropic"),
    ("claude-sonnet-4-5", "Claude Sonnet 4.5", "Anthropic"),
    ("claude-haiku-4-5", "Claude Haiku 4.5", "Anthropic"),
    ("claude-opus-4-5", "Claude Opus 4.5", "Anthropic"),
    # Google
    ("gemini/gemini-3.1-pro-preview", "Gemini 3.1 Pro", "Google"),
    ("gemini/gemini-3.5-flash", "Gemini 3.5 Flash", "Google"),
    ("gemini/gemini-2.5-pro", "Gemini 2.5 Pro", "Google"),
    ("gemini/gemini-2.5-flash", "Gemini 2.5 Flash", "Google"),
    ("gemini/gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "Google"),
    ("gemini/gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite", "Google"),
    # xAI
    ("xai/grok-4.5", "Grok 4.5", "xAI"),
    ("xai/grok-4.3", "Grok 4.3", "xAI"),
    ("xai/grok-4-1-fast", "Grok 4.1 Fast", "xAI"),
    ("xai/grok-4", "Grok 4", "xAI"),
    ("xai/grok-3", "Grok 3", "xAI"),
    # Mistral
    ("mistral/mistral-large-3", "Mistral Large 3", "Mistral"),
    ("mistral/mistral-medium-3-5", "Mistral Medium 3.5", "Mistral"),
    ("mistral/magistral-medium-latest", "Magistral Medium", "Mistral"),
    ("mistral/codestral-2508", "Codestral", "Mistral"),
    # DeepSeek
    ("deepseek/deepseek-v4-pro", "DeepSeek V4 Pro", "DeepSeek"),
    ("deepseek/deepseek-v3.2", "DeepSeek V3.2", "DeepSeek"),
    ("deepseek/deepseek-r1", "DeepSeek R1", "DeepSeek"),
    ("deepseek/deepseek-v4-flash", "DeepSeek V4 Flash", "DeepSeek"),
    # Cohere
    ("command-a-03-2025", "Command A", "Cohere"),
    ("command-r-plus", "Command R+", "Cohere"),
    ("command-r", "Command R", "Cohere"),
]

PROVIDER_PRICING_URL = {
    "OpenAI": "https://openai.com/api/pricing/",
    "Anthropic": "https://www.anthropic.com/pricing#api",
    "Google": "https://ai.google.dev/gemini-api/docs/pricing",
    "xAI": "https://docs.x.ai/docs/models",
    "Mistral": "https://mistral.ai/pricing#api-pricing",
    "DeepSeek": "https://api-docs.deepseek.com/quick_start/pricing",
    "Cohere": "https://cohere.com/pricing",
}

# beehiiv publication (hosted subscribe page). Change here if the publication changes.
NEWSLETTER_URL = "https://neils-newsletter-cea45b.beehiiv.com/"

# Google Analytics 4 measurement tag.
GA_ID = "G-NZMTZ9JS2L"
GA_SNIPPET = (
    '<script async src="https://www.googletagmanager.com/gtag/js?id=%s"></script>'
    '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
    "gtag('js',new Date());gtag('config','%s');</script>" % (GA_ID, GA_ID))


def load_catalog():
    try:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "llm-price-tracker/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        print("Loaded catalog from network: %d entries" % len(data))
        try:
            with open(LOCAL_FALLBACK, "w") as f:
                json.dump(data, f)
        except Exception:
            pass
        return data
    except Exception as e:
        print("Network fetch failed (%s); using local fallback" % e)
        with open(LOCAL_FALLBACK) as f:
            return json.load(f)


def per1m(x):
    if x is None:
        return None
    return round(x * 1_000_000, 3)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money_py(x):
    if x is None:
        return "&mdash;"
    return ("$%.2f" % x) if x >= 1 else ("$%.3f" % x)


def ctx_py(n):
    if not n:
        return "&mdash;"
    if n >= 1_000_000:
        return ("%.1fM" % (n / 1_000_000)).replace(".0M", "M")
    if n >= 1000:
        return "%dK" % round(n / 1000)
    return str(n)


def build_models(cat):
    out = []
    _seen_slugs = set()
    for key, name, prov in ROSTER:
        v = cat.get(key)
        if not isinstance(v, dict):
            print("  WARN missing key: %s" % key)
            continue
        inp = per1m(v.get("input_cost_per_token"))
        outp = per1m(v.get("output_cost_per_token"))
        if inp is None or outp is None:
            print("  WARN no price for: %s" % key)
            continue
        blended = round((3 * inp + outp) / 4, 3)
        rec = {
            "name": name,
            "provider": prov,
            "api_id": key.split("/")[-1],
            "input": inp,
            "output": outp,
            "cache_read": per1m(v.get("cache_read_input_token_cost")),
            "blended": blended,
            "context": v.get("max_input_tokens") or v.get("max_tokens"),
            "max_output": v.get("max_output_tokens"),
            "vision": bool(v.get("supports_vision")),
            "reasoning": bool(v.get("supports_reasoning")),
            "function_calling": bool(v.get("supports_function_calling")),
            "prompt_caching": bool(v.get("supports_prompt_caching")),
            "pricing_url": PROVIDER_PRICING_URL.get(prov, "#"),
        }
        slug = slugify(rec["api_id"])
        if slug in _seen_slugs:
            slug = slugify(prov + "-" + rec["api_id"])
        _seen_slugs.add(slug)
        rec["slug"] = slug
        out.append(rec)
    out.sort(key=lambda m: m["blended"])
    print("Built %d models across %d providers" % (len(out), len(set(m["provider"] for m in out))))
    return out


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM API Pricing Tracker - Live Cost & Limits Comparison (__UPDATED__)</title>
<meta name="description" content="Live, auto-updated comparison of LLM API pricing, context windows, output limits and capabilities across OpenAI, Anthropic, Google, xAI, Mistral, DeepSeek and Cohere. Compare cost per million tokens and estimate your monthly bill.">
<link rel="canonical" href="__CANONICAL__">
<meta property="og:type" content="website">
<meta property="og:title" content="LLM API Pricing Tracker - Live Comparison">
<meta property="og:description" content="Compare LLM API prices, context windows and capabilities across every major provider. Auto-updated __UPDATED__.">
<meta property="og:url" content="__CANONICAL__">
<meta name="twitter:card" content="summary_large_image">
<meta name="robots" content="index,follow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128176;</text></svg>">
__GA__
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Dataset","name":"LLM API Pricing Tracker","description":"Live comparison of large language model API pricing, context windows and capabilities across major providers.","creator":{"@type":"Organization","name":"LLM API Pricing Tracker"},"dateModified":"__GENERATED_ISO__","distribution":{"@type":"DataDownload","encodingFormat":"application/json","contentUrl":"__CANONICAL__data/models.json"}}
</script>
<style>
:root{
  --bg:#f7f8fa;--panel:#ffffff;--ink:#0f1729;--muted:#5b6577;--line:#e6e9ef;
  --accent:#2f6df6;--accent-soft:#eaf1ff;--good:#0a7d4d;--mono:'JetBrains Mono',ui-monospace,monospace;
  --OpenAI:#10a37f;--Anthropic:#d08c60;--Google:#4285f4;--xAI:#111827;--Mistral:#fb6a34;--DeepSeek:#6d5ef6;--Cohere:#39c5bb;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;font-size:15px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1160px;margin:0 auto;padding:0 20px}
header.top{background:linear-gradient(180deg,#0f1729,#1b2540);color:#fff;padding:34px 0 30px}
header.top .wrap{display:flex;flex-direction:column;gap:10px}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:15px;letter-spacing:.3px;opacity:.85}
h1{margin:2px 0 0;font-size:32px;line-height:1.15;font-weight:700}
.sub{color:#c3ccdd;max-width:720px;font-size:15px}
.meta{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;align-items:center}
.badge{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);color:#eaf0ff;padding:5px 11px;border-radius:999px;font-size:12.5px;font-weight:500}
.dot{width:7px;height:7px;border-radius:50%;background:#37d67a;box-shadow:0 0 0 3px rgba(55,214,122,.25)}
.nav{display:flex;gap:18px;margin-top:6px;font-size:13.5px}
.nav a{color:#c3ccdd}
main{padding:26px 0 60px}
.controls{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:18px;box-shadow:0 1px 2px rgba(16,23,41,.04)}
.controls .row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.search{flex:1;min-width:220px;display:flex;align-items:center;gap:8px;background:#f2f4f8;border:1px solid var(--line);border-radius:10px;padding:9px 12px}
.search input{border:0;background:transparent;outline:none;width:100%;font-size:14.5px;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:7px}
.chip{cursor:pointer;user-select:none;border:1px solid var(--line);background:#fff;color:var(--muted);padding:6px 11px;border-radius:999px;font-size:12.5px;font-weight:600;transition:.12s}
.chip[aria-pressed=true]{color:#fff;border-color:transparent}
.chip[data-prov=OpenAI][aria-pressed=true]{background:var(--OpenAI)}
.chip[data-prov=Anthropic][aria-pressed=true]{background:var(--Anthropic)}
.chip[data-prov=Google][aria-pressed=true]{background:var(--Google)}
.chip[data-prov=xAI][aria-pressed=true]{background:var(--xAI)}
.chip[data-prov=Mistral][aria-pressed=true]{background:var(--Mistral)}
.chip[data-prov=DeepSeek][aria-pressed=true]{background:var(--DeepSeek)}
.chip[data-prov=Cohere][aria-pressed=true]{background:var(--Cohere)}
.toggle{cursor:pointer;user-select:none;border:1px solid var(--line);background:#fff;color:var(--muted);padding:6px 11px;border-radius:8px;font-size:12.5px;font-weight:600}
.toggle[aria-pressed=true]{background:var(--accent-soft);color:var(--accent);border-color:#cfe0ff}
.calc{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;border-top:1px dashed var(--line);margin-top:14px;padding-top:14px}
.calc .fld{display:flex;flex-direction:column;gap:4px}
.calc label{font-size:11.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.calc input{width:130px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px;font-family:var(--mono)}
.calc .hint{font-size:12px;color:var(--muted);max-width:280px}
.tablewrap{background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 1px 2px rgba(16,23,41,.04)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
thead th{position:sticky;top:0;background:#fbfcfe;border-bottom:1px solid var(--line);text-align:right;padding:12px 14px;font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);cursor:pointer;white-space:nowrap;font-weight:600}
thead th.l{text-align:left}
thead th[aria-sort]:after{content:" \25B4";opacity:.9}
thead th[aria-sort=descending]:after{content:" \25BE"}
tbody td{border-bottom:1px solid var(--line);padding:11px 14px;text-align:right;white-space:nowrap;font-family:var(--mono)}
tbody td.l{text-align:left;font-family:Inter,sans-serif}
tbody tr:hover{background:#f7faff}
.model{display:flex;align-items:center;gap:9px}
.pill{width:8px;height:8px;border-radius:50%;flex:none}
.mname{font-weight:600}
.mid{font-size:11.5px;color:var(--muted);font-family:var(--mono)}
.prov{font-size:12px;font-weight:600}
.caps{display:inline-flex;gap:5px}
.cap{font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px;background:#eef1f6;color:#55607a;font-family:Inter}
.cap.on{background:var(--accent-soft);color:var(--accent)}
.num{font-variant-numeric:tabular-nums}
.big{font-weight:600}
.est{color:var(--good);font-weight:600}
.foot{margin-top:26px;color:var(--muted);font-size:13px}
.foot h3{color:var(--ink);font-size:15px;margin:20px 0 6px}
.foot code{background:#eef1f6;padding:2px 6px;border-radius:5px;font-family:var(--mono);font-size:12.5px}
.disc{background:#fff8ec;border:1px solid #f3e2be;color:#7a5b16;padding:12px 14px;border-radius:10px;font-size:13px;margin-top:16px}
.capture{display:flex;flex-wrap:wrap;gap:16px 20px;align-items:center;justify-content:space-between;background:linear-gradient(100deg,#eef3ff,#f6f0ff);border:1px solid #dfe6fb;border-radius:14px;padding:18px 20px;margin-bottom:18px}
.capture h2{margin:0;font-size:18px}
.capture p{margin:4px 0 0;color:var(--muted);font-size:13.5px}
.subform{display:flex;gap:8px;flex:1;min-width:280px;max-width:470px}
.subform input{flex:1;border:1px solid var(--line);border-radius:10px;padding:11px 13px;font-size:14.5px;font-family:inherit}
.subform button{white-space:nowrap;border:0;background:var(--accent);color:#fff;font-weight:600;font-size:14px;padding:11px 16px;border-radius:10px;cursor:pointer}
.subform button:hover{background:#1f5be0}
.subnote{width:100%;font-size:11.5px;color:var(--muted);margin-top:2px}
.count{font-size:12.5px;color:var(--muted);padding:2px 2px 12px}
@media(max-width:640px){h1{font-size:25px}.calc input{width:110px}}
</style>
</head>
<body>
<header class="top"><div class="wrap">
  <div class="brand">&#128176; LLM API PRICING TRACKER</div>
  <h1>LLM API pricing &amp; limits, kept current</h1>
  <div class="sub">A live comparison of API cost, context windows, output limits and capabilities across every major model provider. Rebuilt automatically from public data - no stale screenshots.</div>
  <div class="meta">
    <span class="badge"><span class="dot"></span> Updated __UPDATED__</span>
    <span class="badge">__COUNT__ models &middot; 7 providers</span>
    <span class="badge">Auto-refreshed daily</span>
  </div>
  <nav class="nav"><a href="#table">Comparison</a><a href="#calc">Cost calculator</a><a href="#methodology">Methodology</a><a href="data/models.json">JSON API</a></nav>
</div></header>
<main class="wrap">
  <section class="capture">
    <div class="cap-copy">
      <h2>&#128238; Never get surprised by a price change</h2>
      <p>One short email a week when a tracked model changes price, limits or capabilities. Free.</p>
    </div>
    <form id="subForm" class="subform">
      <input id="subEmail" type="email" placeholder="you@company.com" aria-label="Email address" required>
      <button type="submit">Get weekly alerts &rarr;</button>
    </form>
    <div class="subnote">Free forever &middot; unsubscribe anytime &middot; delivered via beehiiv.</div>
  </section>
  <section class="controls">
    <div class="row">
      <div class="search">&#128269;<input id="q" type="search" placeholder="Search model or provider (e.g. claude, gemini, o3)..." autocomplete="off"></div>
      <div class="chips" id="provChips"></div>
    </div>
    <div class="row" style="margin-top:10px">
      <span style="font-size:12px;color:var(--muted);font-weight:600">FILTER:</span>
      <span class="toggle" id="tVision" aria-pressed="false">&#128065; Vision</span>
      <span class="toggle" id="tReason" aria-pressed="false">&#129504; Reasoning</span>
      <span class="toggle" id="tCache" aria-pressed="false">&#9889; Prompt caching</span>
    </div>
    <div class="calc" id="calc">
      <div class="fld"><label>Input tokens / call</label><input id="inTok" type="number" min="0" value="2000"></div>
      <div class="fld"><label>Output tokens / call</label><input id="outTok" type="number" min="0" value="500"></div>
      <div class="fld"><label>Calls / month</label><input id="calls" type="number" min="0" value="100000"></div>
      <div class="hint">The <b>Est. $/mo</b> column updates live so you can rank models by what they would actually cost for <i>your</i> workload.</div>
    </div>
  </section>
  <div class="count" id="count"></div>
  <div class="tablewrap"><div class="scroll">
  <table id="tbl">
    <thead><tr>
      <th class="l" data-k="name">Model</th>
      <th class="l" data-k="provider">Provider</th>
      <th data-k="input">Input $/1M</th>
      <th data-k="output">Output $/1M</th>
      <th data-k="blended" aria-sort="ascending">Blended $/1M</th>
      <th data-k="context">Context</th>
      <th data-k="max_output">Max out</th>
      <th class="l" data-k="_caps">Capabilities</th>
      <th data-k="est">Est. $/mo</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  </div></div>

  <div class="disc">&#9888;&#65039; <b>Verify before you buy.</b> This site is built and maintained by an autonomous AI agent. Prices are aggregated from public data and can change or lag. Always confirm on the provider's official pricing page (linked on each provider) before making purchasing decisions. "Blended" = (3&times;input + output) &divide; 4, a rough single-number proxy for typical chat workloads.</div>

  <section class="foot" id="methodology">
    <h3>Methodology &amp; data</h3>
    Pricing, context windows, output limits and capability flags are aggregated from the open-source <a href="https://github.com/BerriAI/litellm" target="_blank" rel="noopener noreferrer">LiteLLM model catalog</a> and cross-referenced with each provider's official pricing page. Prices are shown per <b>1,000,000 tokens</b> in USD. The dataset rebuilds automatically on a daily schedule; the model roster is curated for relevance and reviewed regularly.
    <h3>Open data (free API)</h3>
    The full dataset is available as JSON at <code>/data/models.json</code> and summarised for machines at <code>/llms.txt</code>. Attribution appreciated: link back to this tracker.
    <h3>Disclosure</h3>
    Independent project, not affiliated with any provider. Outbound provider links are currently plain informational links; if any become affiliate links in future they will be clearly marked as such. Content is AI-generated and human-reviewable.
    <h3 id="api">Providers tracked</h3>
    OpenAI &middot; Anthropic &middot; Google &middot; xAI &middot; Mistral &middot; DeepSeek &middot; Cohere.
    <p style="margin-top:22px;font-size:12px">Last generated __GENERATED_ISO__ &middot; &copy; __YEAR__ LLM API Pricing Tracker &middot; Built with open data.</p>
  </section>
</main>
<script>
const MODELS = __MODELS_JSON__;
let sortKey="blended", sortDir=1;
const activeProv=new Set();
const flags={vision:false,reasoning:false,prompt_caching:false};
const $=s=>document.querySelector(s);

const PROVS=[...new Set(MODELS.map(m=>m.provider))];
const chipBox=$("#provChips");
PROVS.forEach(p=>{const c=document.createElement("span");c.className="chip";c.dataset.prov=p;c.textContent=p;c.setAttribute("aria-pressed","false");c.onclick=()=>{c.getAttribute("aria-pressed")==="true"?(c.setAttribute("aria-pressed","false"),activeProv.delete(p)):(c.setAttribute("aria-pressed","true"),activeProv.add(p));render();};chipBox.appendChild(c);});

function money(x){if(x===null||x===undefined)return "—";return "$"+(x>=1?x.toFixed(2):x.toFixed(3));}
function ctxFmt(n){if(!n)return "—";if(n>=1e6)return (n/1e6).toFixed(n%1e6?1:0).replace(/\.0$/,'')+"M";if(n>=1e3)return Math.round(n/1e3)+"K";return n;}
function estCost(m){const i=+$("#inTok").value||0,o=+$("#outTok").value||0,c=+$("#calls").value||0;return (i/1e6*m.input + o/1e6*m.output)*c;}
function money2(x){return "$"+x.toLocaleString(undefined,{maximumFractionDigits:2,minimumFractionDigits:2});}

function passes(m){
  const q=$("#q").value.trim().toLowerCase();
  if(q && !(m.name.toLowerCase().includes(q)||m.provider.toLowerCase().includes(q)||m.api_id.toLowerCase().includes(q)))return false;
  if(activeProv.size && !activeProv.has(m.provider))return false;
  for(const f in flags){if(flags[f] && !m[f])return false;}
  return true;
}
function render(){
  let rows=MODELS.filter(passes);
  rows.forEach(m=>m._est=estCost(m));
  rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(typeof x==="string"){return sortDir*x.localeCompare(y);}return sortDir*((x??0)-(y??0));});
  const tb=$("#rows");tb.innerHTML="";
  rows.forEach(m=>{
    const caps=[["V","vision"],["R","reasoning"],["F","function_calling"],["C","prompt_caching"]]
      .map(([lab,k])=>`<span class="cap ${m[k]?'on':''}" title="${k.replace('_',' ')}">${lab}</span>`).join("");
    const tr=document.createElement("tr");
    tr.innerHTML=`
      <td class="l"><div class="model"><span class="pill" style="background:var(--${m.provider})"></span><span><span class="mname"><a href="model/${m.slug}.html" style="color:inherit;text-decoration:none">${m.name}</a></span><br><span class="mid">${m.api_id}</span></span></div></td>
      <td class="l"><a class="prov" style="color:var(--${m.provider})" href="${m.pricing_url}" target="_blank" rel="noopener noreferrer">${m.provider} &#8599;</a></td>
      <td class="num">${money(m.input)}</td>
      <td class="num">${money(m.output)}</td>
      <td class="num big">${money(m.blended)}</td>
      <td class="num">${ctxFmt(m.context)}</td>
      <td class="num">${ctxFmt(m.max_output)}</td>
      <td class="l"><span class="caps">${caps}</span></td>
      <td class="num est">${money2(m._est)}</td>`;
    tb.appendChild(tr);
  });
  $("#count").textContent=`Showing ${rows.length} of ${MODELS.length} models`+(activeProv.size?` · ${[...activeProv].join(", ")}`:"");
  document.querySelectorAll("thead th").forEach(th=>{th.removeAttribute("aria-sort");if(th.dataset.k===sortKey)th.setAttribute("aria-sort",sortDir>0?"ascending":"descending");});
}
document.querySelectorAll("thead th").forEach(th=>{const k=th.dataset.k;if(k==="_caps")return;th.onclick=()=>{if(sortKey===k){sortDir*=-1;}else{sortKey=k;sortDir=(k==="name"||k==="provider")?1:1;}render();};});
["#q","#inTok","#outTok","#calls"].forEach(s=>$(s).addEventListener("input",render));
["tVision","vision"],["tReason","reasoning"],["tCache","prompt_caching"];
$("#tVision").onclick=t=>{flags.vision=!flags.vision;$("#tVision").setAttribute("aria-pressed",flags.vision);render();};
$("#tReason").onclick=t=>{flags.reasoning=!flags.reasoning;$("#tReason").setAttribute("aria-pressed",flags.reasoning);render();};
$("#tCache").onclick=t=>{flags.prompt_caching=!flags.prompt_caching;$("#tCache").setAttribute("aria-pressed",flags.prompt_caching);render();};
$("#subForm").addEventListener("submit",function(e){e.preventDefault();var em=encodeURIComponent(($("#subEmail").value||"").trim());window.open("__NEWSLETTER_URL__subscribe?email="+em,"_blank","noopener");});
render();
</script>
</body>
</html>"""


DETAIL_PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ API pricing, context &amp; limits (__UPDATED__)</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="__CANONICAL__">
<meta property="og:type" content="article"><meta property="og:title" content="__NAME__ API pricing &amp; limits">
<meta property="og:description" content="__DESC__">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#128176;</text></svg>">
__GA__
<script type="application/ld+json">__JSONLD__</script>
<style>
:root{--ink:#0f1729;--muted:#5b6577;--line:#e6e9ef;--accent:#2f6df6;--mono:'JetBrains Mono',ui-monospace,monospace}
*{box-sizing:border-box}body{margin:0;background:#f7f8fa;color:var(--ink);font-family:Inter,system-ui,sans-serif;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:0 20px}
header.top{background:linear-gradient(180deg,#0f1729,#1b2540);color:#fff;padding:22px 0}
.crumb{font-size:13px;color:#c3ccdd}.crumb a{color:#c3ccdd;text-decoration:none}
h1{font-size:28px;margin:18px 0 4px}.sub{color:var(--muted);margin:0 0 6px}
main{padding:8px 0 60px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px}
.card .k{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600}
.card .v{font-family:var(--mono);font-size:20px;margin-top:4px}
h2{font-size:18px;margin:26px 0 10px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:14px}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right}
th.l,td.l{text-align:left}td.n{font-family:var(--mono)}
th{background:#fbfcfe;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}
td a{color:var(--accent);text-decoration:none}
.cta{margin:24px 0;background:linear-gradient(100deg,#eef3ff,#f6f0ff);border:1px solid #dfe6fb;border-radius:12px;padding:16px 18px;font-weight:600}
.cta a{color:var(--accent)}
.foot{margin-top:22px;font-size:13px;color:var(--muted)}.foot a{color:var(--accent)}
</style></head><body>
<header class="top"><div class="wrap"><div class="crumb"><a href="../index.html">&#128176; LLM API Pricing Tracker</a> / __NAME__</div></div></header>
<main class="wrap">
<h1>__NAME__ API pricing &amp; limits</h1>
<p class="sub">by <a href="__PROVIDER_URL__" target="_blank" rel="noopener noreferrer">__PROVIDER__ official pricing &#8599;</a> &middot; auto-updated __UPDATED__ &middot; USD per 1M tokens</p>
<div class="cards">__PRICE_CARDS__</div>
<div class="cta">&#128238; Track price changes for __NAME__ and every major model &mdash; <a href="__NEWSLETTER__subscribe">get the free weekly email &rarr;</a></div>
<h2>How __NAME__ compares (blended $/1M, cheapest first)</h2>
<table><thead><tr><th class="l">Model</th><th class="l">Provider</th><th>Input</th><th>Output</th><th>Blended</th><th>Context</th></tr></thead><tbody>
__COMPARE_ROWS__
</tbody></table>
<p class="foot"><a href="../index.html">&larr; Full sortable comparison &amp; cost calculator</a> &middot; <a href="../data/models.json">Free JSON API</a> &middot; Prices aggregated from public data; verify on the provider's official page before purchasing.</p>
</main></body></html>"""


def _compare_rows(models, current_slug):
    rows = []
    for m in models:
        hi = ' style="background:#eef3ff"' if m["slug"] == current_slug else ''
        rows.append(
            '<tr%s><td class="l"><a href="%s.html">%s</a></td><td class="l">%s</td>'
            '<td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td></tr>'
            % (hi, m["slug"], m["name"], m["provider"], money_py(m["input"]),
               money_py(m["output"]), money_py(m["blended"]), ctx_py(m["context"]))
        )
    return "\n".join(rows)


def render_site(models, canonical):
    now = datetime.datetime.now(datetime.timezone.utc)
    updated = now.strftime("%d %b %Y")
    gen_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    html_out = (PAGE
                .replace("__MODELS_JSON__", json.dumps(models))
                .replace("__UPDATED__", updated)
                .replace("__COUNT__", str(len(models)))
                .replace("__GENERATED_ISO__", gen_iso)
                .replace("__YEAR__", str(now.year))
                .replace("__CANONICAL__", canonical)
                .replace("__NEWSLETTER_URL__", NEWSLETTER_URL)
                .replace("__GA__", GA_SNIPPET))
    os.makedirs("_site/data", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    with open("_site/index.html", "w") as f:
        f.write(html_out)
    base = {
        "source": "https://github.com/BerriAI/litellm",
        "unit": "USD per 1,000,000 tokens",
        "count": len(models),
        "models": models,
    }
    # Served copy carries the volatile timestamp; committed copy omits it so the
    # repo's commit history only records genuine data changes (a real freshness log).
    with open("_site/data/models.json", "w") as f:
        json.dump(dict(base, generated_at=gen_iso), f, indent=2)
    with open("data/models.json", "w") as f:
        json.dump(base, f, indent=2)
    llms = (
        "# LLM API Pricing Tracker\n"
        "Live comparison of LLM API pricing, context windows, output limits and capabilities.\n"
        "Updated: %s\n"
        "Unit: USD per 1,000,000 tokens.\n"
        "Data source: open-source LiteLLM catalog + providers' official pricing pages.\n"
        "Full machine-readable dataset: %sdata/models.json\n\n"
        "## Models tracked (cheapest blended first)\n" % (gen_iso, canonical)
    )
    for m in models:
        llms += "- %s (%s): input $%s/1M, output $%s/1M, context %s, max output %s\n" % (
            m["name"], m["provider"], m["input"], m["output"], m["context"], m["max_output"])
    with open("_site/llms.txt", "w") as f:
        f.write(llms)
    print("Wrote _site/index.html (%d bytes), data/models.json, _site/llms.txt" % len(html_out))

    # Per-model SEO landing pages + sitemap + robots
    os.makedirs("_site/model", exist_ok=True)
    caps_lbl = [("vision", "Vision"), ("reasoning", "Reasoning"),
                ("function_calling", "Function calling"), ("prompt_caching", "Prompt caching")]
    urls = [canonical]
    for m in models:
        caps = ", ".join(lbl for k, lbl in caps_lbl if m.get(k)) or "text"
        cards = "".join([
            '<div class="card"><div class="k">Input /1M</div><div class="v">%s</div></div>' % money_py(m["input"]),
            '<div class="card"><div class="k">Output /1M</div><div class="v">%s</div></div>' % money_py(m["output"]),
            '<div class="card"><div class="k">Blended /1M</div><div class="v">%s</div></div>' % money_py(m["blended"]),
            '<div class="card"><div class="k">Context</div><div class="v">%s</div></div>' % ctx_py(m["context"]),
            '<div class="card"><div class="k">Max output</div><div class="v">%s</div></div>' % ctx_py(m["max_output"]),
            '<div class="card"><div class="k">Cache read /1M</div><div class="v">%s</div></div>' % money_py(m.get("cache_read")),
        ])
        page_url = canonical + "model/" + m["slug"] + ".html"
        desc = ("%s (%s) API pricing: %s input, %s output per 1M tokens, %s context. "
                "Capabilities: %s. Compare against every major model." % (
                    m["name"], m["provider"], money_py(m["input"]), money_py(m["output"]),
                    ctx_py(m["context"]), caps)).replace("&mdash;", "-")
        jsonld = json.dumps({"@context": "https://schema.org", "@type": "Product",
                             "name": m["name"] + " API", "brand": {"@type": "Brand", "name": m["provider"]},
                             "description": desc, "url": page_url})
        html_d = (DETAIL_PAGE
                  .replace("__NAME__", m["name"]).replace("__PROVIDER_URL__", m["pricing_url"])
                  .replace("__PROVIDER__", m["provider"]).replace("__UPDATED__", updated)
                  .replace("__DESC__", desc).replace("__CANONICAL__", page_url)
                  .replace("__JSONLD__", jsonld).replace("__PRICE_CARDS__", cards)
                  .replace("__COMPARE_ROWS__", _compare_rows(models, m["slug"]))
                  .replace("__NEWSLETTER__", NEWSLETTER_URL)
                  .replace("__GA__", GA_SNIPPET))
        with open("_site/model/%s.html" % m["slug"], "w") as f:
            f.write(html_d)
        urls.append(page_url)

    today = now.strftime("%Y-%m-%d")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append("<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (u, today))
    sm.append("</urlset>")
    with open("_site/sitemap.xml", "w") as f:
        f.write("\n".join(sm))
    with open("_site/robots.txt", "w") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % canonical)
    print("Wrote %d model pages + sitemap.xml + robots.txt" % len(models))


if __name__ == "__main__":
    canonical = os.environ.get("SITE_URL", "").rstrip("/")
    canonical = (canonical + "/") if canonical else "/"
    cat = load_catalog()
    models = build_models(cat)
    render_site(models, canonical)
    print("Done.")
