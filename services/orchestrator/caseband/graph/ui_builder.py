"""ui_builder — the UI-builder agent. A case is not a chat: this turns a RichCase
into a self-contained, accessible, interactive HTML page a student can actually
work in — exhibits as data tables, a LIVE activity-costing worksheet they fill in
themselves, and a staged player that reveals new information as they advance.

Deterministic by design: it emits real, dependency-free HTML/CSS/JS (no fragile
LLM-authored code), so 'deploy straight away' is reliable. The page never ships
the answer — no allocated totals, no answer_key, no expected_insight, no rubric
internals. The worksheet computes the allocation CLIENT-side from the visible
inputs, so the student does the analysis; that's the teaching 'aha', not a leak."""
from __future__ import annotations
import html
import json
import os

from ..models.rich_case import RichCase


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _exhibit_html(e) -> str:
    if e.kind == "table" and e.rows:
        head = "".join(f"<th>{_esc(c)}</th>" for c in e.columns)
        body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
                       for row in e.rows)
        table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    else:
        table = ""
    src = (f'<a class="src" href="{_esc(e.source_url)}" target="_blank" rel="noopener">'
           f"source</a>") if e.source_url else ""
    return (f'<figure class="exhibit"><figcaption><b>{_esc(e.key)}.</b> '
            f"{_esc(e.title)} {src}</figcaption>{table}"
            f'<p class="note">{_esc(e.note)}</p></figure>')


def _worksheet_html(backbone: dict) -> str:
    """A live ABC worksheet: the student enters the overhead pool allocation and the
    page computes fully-loaded cost + ranking. Mirrors tools.backbone.allocate, but
    only from the visible direct costs + driver volumes."""
    acts = backbone.get("activities") or []
    pool = backbone.get("overhead_pool") or 0
    rows = "".join(
        f'<tr data-key="{_esc(a.get("key"))}">'
        f'<td>{_esc(a.get("label"))}</td>'
        f'<td class="num">{_esc(int(a.get("direct_cost", 0))):}</td>'
        f'<td class="num">{_esc(int(a.get("overhead_driver", 0)))}</td>'
        f'<td class="num alloc">—</td><td class="num total">—</td>'
        f'<td class="rank">—</td></tr>'
        for a in acts)
    data = json.dumps([{"key": a.get("key"), "label": a.get("label"),
                        "direct": float(a.get("direct_cost", 0)),
                        "driver": float(a.get("overhead_driver", 0))} for a in acts])
    return f'''
<section class="card worksheet" aria-labelledby="ws-h">
  <h2 id="ws-h">Activity-based costing worksheet</h2>
  <p>Overhead pool to allocate: <b>${int(pool):,}</b>. Allocate it across activities by each
     activity's share of total driver volume, then rank by fully-loaded cost.</p>
  <table>
    <thead><tr><th>Activity</th><th>Direct cost</th><th>Driver vol.</th>
      <th>Allocated OH</th><th>Fully-loaded</th><th>Rank</th></tr></thead>
    <tbody id="ws-body">{rows}</tbody>
  </table>
  <button id="ws-run" class="btn">Allocate &amp; rank</button>
  <p id="ws-out" class="out" role="status" aria-live="polite"></p>
</section>
<script>
(function(){{
  var POOL = {int(pool)}, ACTS = {data};
  document.getElementById('ws-run').addEventListener('click', function(){{
    var totalDriver = ACTS.reduce(function(s,a){{return s+a.driver;}},0) || 1;
    var ranked = ACTS.map(function(a){{
      var oh = POOL * (a.driver/totalDriver);
      return {{key:a.key, label:a.label, alloc:oh, total:a.direct+oh}};
    }}).sort(function(x,y){{return y.total-x.total;}});
    var rankOf = {{}}; ranked.forEach(function(r,i){{rankOf[r.key]=i+1;}});
    document.querySelectorAll('#ws-body tr').forEach(function(tr){{
      var r = ranked.find(function(z){{return z.key===tr.dataset.key;}});
      tr.querySelector('.alloc').textContent = '$'+Math.round(r.alloc).toLocaleString();
      tr.querySelector('.total').textContent = '$'+Math.round(r.total).toLocaleString();
      tr.querySelector('.rank').textContent = '#'+rankOf[r.key];
      tr.classList.toggle('top', rankOf[r.key]===1);
    }});
    var top = ranked[0];
    document.getElementById('ws-out').textContent =
      'Largest fully-loaded cost: '+top.label+' ($'+Math.round(top.total).toLocaleString()+
      '). Is that what you expected?';
  }});
}})();
</script>'''


def _stages_html(case: RichCase) -> str:
    """A staged player: one stage visible at a time; advancing reveals the next
    stage's inject. The reveal text is in the markup but hidden until reached."""
    blocks = []
    for i, s in enumerate(case.stages):
        reveal = (f'<div class="reveal"><b>New information:</b> {_esc(s.reveal_on_entry)}</div>'
                  if s.reveal_on_entry and i > 0 else "")
        ex = ", ".join(s.exhibits)
        ex_line = f'<p class="muted">Refer to exhibit(s): {_esc(ex)}</p>' if ex else ""
        blocks.append(
            f'<article class="stage" data-idx="{i}" {"hidden" if i else ""}>'
            f"{reveal}"
            f"<h2>Stage {i+1}: {_esc(s.title)}</h2>"
            f'<p class="situation">{_esc(s.situation)}</p>'
            f'<p class="dilemma"><b>Decision:</b> {_esc(s.dilemma)}</p>'
            f'<p class="task">{_esc(s.task)}</p>{ex_line}'
            f'<label class="lbl">Your response<textarea rows="5" '
            f'aria-label="Your response for stage {i+1}"></textarea></label>'
            f'<button class="btn next">{"Submit case" if i==len(case.stages)-1 else "Submit &amp; continue"}</button>'
            f"</article>")
    return f'''
<section class="card player" aria-labelledby="pl-h">
  <h2 id="pl-h">The case <span class="muted" id="pl-prog">(stage 1 of {len(case.stages)})</span></h2>
  {''.join(blocks)}
  <div id="pl-done" hidden class="done">You've completed the case. Your responses are
     recorded for feedback.</div>
</section>
<script>
(function(){{
  var stages = Array.prototype.slice.call(document.querySelectorAll('.stage'));
  var prog = document.getElementById('pl-prog');
  stages.forEach(function(st, i){{
    st.querySelector('.next').addEventListener('click', function(){{
      st.hidden = true;
      if (i+1 < stages.length) {{
        stages[i+1].hidden = false;
        prog.textContent = '(stage '+(i+2)+' of '+stages.length+')';
        stages[i+1].scrollIntoView({{behavior:'smooth', block:'start'}});
      }} else {{
        document.getElementById('pl-done').hidden = false;
        prog.textContent = '(complete)';
      }}
    }});
  }});
}})();
</script>'''


_CSS = """
:root{--ink:#11151f;--mut:#5d6678;--line:#e3e7ee;--navy:#3b5bdb;--bg:#fff;--panel:#f7f9fc;--ok:#2f9e69}
*{box-sizing:border-box}body{margin:0;font:15px/1.6 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--panel)}
.wrap{max-width:880px;margin:0 auto;padding:28px 20px 80px}
.card{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:0 0 18px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:18px;margin:0 0 10px}
.label{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--navy)}
.muted,.note{color:var(--mut)}.note{font-size:13px;margin:8px 0 0}
table{width:100%;border-collapse:collapse;margin:6px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left}th{background:var(--panel);font-weight:600}
td.num,th:nth-child(n+2){text-align:right;font-variant-numeric:tabular-nums}
tr.top{background:rgba(47,158,105,.12)}tr.top .rank{color:var(--ok);font-weight:700}
.exhibit{margin:0 0 14px}figcaption{font-size:14px;margin:0 0 4px}
.btn{margin-top:12px;background:var(--navy);color:#fff;border:0;border-radius:8px;padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer}
.btn:hover{background:#2f4cc0}
textarea{display:block;width:100%;margin-top:6px;border:1px solid var(--line);border-radius:8px;padding:9px;font:inherit;resize:vertical}
.lbl{display:block;margin-top:12px;font-weight:600}
.reveal{background:rgba(59,91,219,.08);border:1px solid rgba(59,91,219,.3);border-radius:8px;padding:12px 14px;margin:0 0 12px}
.dilemma{margin:10px 0}.out{margin-top:10px;font-weight:600}
.src{font-size:12px;color:var(--navy);font-weight:600;margin-left:6px}
.protag{color:var(--mut);font-size:14px;margin:2px 0 0}
.obj{margin:6px 0 0;padding-left:20px}.obj li{margin:3px 0}
.done{background:rgba(47,158,105,.1);border:1px solid rgba(47,158,105,.4);border-radius:8px;padding:14px}
"""


def render(case: RichCase) -> str:
    """Return a complete, self-contained interactive HTML document for the case."""
    c = case.company
    objectives = "".join(f"<li>{_esc(o)}</li>" for o in case.learning_objectives)
    exhibits = "".join(_exhibit_html(e) for e in case.exhibits)
    worksheet = _worksheet_html(case.backbone.__dict__) if case.backbone else ""
    people = _people_html(case)
    stages = _stages_html(case)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(case.title)}</title><style>{_CSS}</style></head>
<body><main class="wrap">
  <header class="card">
    <div class="label">Case simulation</div>
    <h1>{_esc(case.title)}</h1>
    <p class="protag">{_esc(c.name)} — {_esc(c.industry)} · {_esc(c.size)}</p>
    <p class="protag"><b>{_esc(c.protagonist)}</b></p>
    <p>{_esc(c.backstory)}</p>
    <p class="dilemma"><b>The situation:</b> {_esc(c.presenting_problem)}</p>
    <div class="label" style="margin-top:14px">What you'll be assessed on</div>
    <ul class="obj">{objectives}</ul>
  </header>
  <section class="card" aria-labelledby="ex-h"><h2 id="ex-h">Exhibits</h2>{exhibits}</section>
  {people}
  {worksheet}
  {stages}
</main></body></html>'''


def _people_html(case: RichCase) -> str:
    """Roster of interviewable characters — PUBLIC info only (never their knowledge).
    The actual Q&A runs through POST /rich-runs/{id}/interview."""
    if not case.personas:
        return ""
    cards = "".join(
        f'<div class="person"><b>{_esc(p.name)}</b> '
        f'<span class="muted">— {_esc(p.role)}</span>'
        f'<p class="note">{_esc(p.public_bio)}</p>'
        f'<button class="btn" data-persona="{_esc(p.key)}" disabled '
        f'title="Interview runs through the app">Interview</button></div>'
        for p in case.personas)
    return (f'<section class="card" aria-labelledby="pp-h"><h2 id="pp-h">People you can '
            f'interview</h2><p class="muted">They know things the exhibits don\'t — but '
            f"ask deliberately; fishing without progress costs you.</p>{cards}</section>")


def render_to_file(case: RichCase, case_id: str, web_root: str | None = None) -> dict:
    """Write the case page under <repo>/web/cases/<case_id>.html and return its
    path + the URL the API serves it at."""
    root = web_root or os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "web")
    out_dir = os.path.abspath(os.path.join(root, "cases"))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{case_id}.html")
    html_doc = render(case)
    with open(path, "w") as fh:
        fh.write(html_doc)
    return {"path": path, "url": f"/cases/{case_id}.html", "bytes": len(html_doc)}
