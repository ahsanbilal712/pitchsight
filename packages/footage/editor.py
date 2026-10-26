"""Drag-to-correct page for a moment file.

    python -m footage.editor <slug> <clip_ms> [--port 8765]

Serves one local page: the frozen broadcast frame with every player's dot, and a top-down pitch with the same dots.
Drag a dot in either view; with a homography in the file the other view follows (pitch <-> image). "Fill missing"
asks the server for the role-prior players (footage.freeze.fill); "Save" writes the moment file back
(data/footage/<slug>/moments/<clip_ms>.json, git-ignored folder). Local only: it binds to 127.0.0.1.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from footage.clips import ROOT, clip_dir
from footage.freeze import fill, load, save

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Moment editor</title><style>
body{font:13px system-ui;margin:12px;background:#111;color:#eee}#wrap{display:flex;gap:12px;flex-wrap:wrap}
.view{position:relative;border:1px solid #444}svg{display:block}.dot{cursor:grab;pointer-events:all}
#bar button{margin-right:8px}#msg{margin-left:8px;color:#9c9}
</style></head><body><div id="bar"><b id="title"></b> <button id="fill">Fill missing</button>
<button id="save">Save</button><span id="msg"></span></div><div id="wrap">
<div class="view"><svg id="img" width="960" height="540"></svg></div>
<div class="view"><svg id="pitch" width="630" height="408" viewBox="-3 -3 111 74"></svg></div></div>
<p>Red: home, blue: away, yellow: ball. Hollow dots are role-prior fills. Drag to correct.</p>
<script>
let M, H, Hi, S = 0.5;
const NS = "http://www.w3.org/2000/svg";
const el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); return e; };
function inv(m){const [a,b,c,d,e,f,g,h,i]=m.flat();const A=e*i-f*h,B=-(d*i-f*g),C=d*h-e*g,det=a*A+b*B+c*C;
 return [[A,-(b*i-c*h),b*f-c*e],[B,a*i-c*g,-(a*f-c*d)],[C,-(a*h-b*g),a*e-b*d]].map(r=>r.map(v=>v/det));}
function ap(m,[x,y]){const w=m[2][0]*x+m[2][1]*y+m[2][2];return[(m[0][0]*x+m[0][1]*y+m[0][2])/w,(m[1][0]*x+m[1][1]*y+m[1][2])/w];}
const toImg = p => p.image || (Hi ? ap(Hi,[p.x,p.y]) : null);
function draw(){
 const img=document.getElementById("img"), pit=document.getElementById("pitch");
 img.innerHTML=""; pit.innerHTML="";
 img.appendChild(el("image",{href:"/frame",width:960,height:540}));
 pit.appendChild(el("rect",{x:0,y:0,width:105,height:68,fill:"#2a6",stroke:"#fff","stroke-width":0.3}));
 for (const [x0,x1] of [[0,16.5],[88.5,105]]) pit.appendChild(el("rect",{x:x0,y:13.84,width:16.5,height:40.32,fill:"none",stroke:"#fff","stroke-width":0.3}));
 pit.appendChild(el("line",{x1:52.5,y1:0,x2:52.5,y2:68,stroke:"#fff","stroke-width":0.3}));
 const items=[...M.players.map(p=>({p,kind:p.team})),{p:M.ball,kind:"ball"}];
 for (const it of items){
  const col=it.kind==="home"?"#e33":it.kind==="away"?"#6cf":"#ff0", hollow=it.p.source==="prior";
  const r=it.kind==="ball"?0.8:1.4, label=it.p.label||it.p.slot||"";
  const d=el("circle",{cx:it.p.x,cy:68-it.p.y,r,fill:hollow?"none":col,stroke:col,"stroke-width":0.4,class:"dot"});
  pit.appendChild(d); drag(d,pit,(x,y)=>{it.p.x=+x.toFixed(2);it.p.y=+(68-y).toFixed(2);if(Hi&&it.p.image)it.p.image=ap(Hi,[it.p.x,it.p.y]).map(Math.round);it.p.source=it.p.source==="prior"?"hand":it.p.source;draw();});
  const t=el("text",{x:it.p.x+1.6,y:68-it.p.y+0.6,fill:"#fff","font-size":2.2}); t.textContent=label; pit.appendChild(t);
  const q=toImg(it.p); if(!q) continue;
  const c=el("circle",{cx:q[0]*S,cy:q[1]*S,r:it.kind==="ball"?4:6,fill:hollow?"none":col,stroke:col,"stroke-width":2,class:"dot","fill-opacity":0.6});
  img.appendChild(c); drag(c,img,(u,v)=>{it.p.image=[Math.round(u/S),Math.round(v/S)];if(H){const [x,y]=ap(H,it.p.image);it.p.x=+x.toFixed(2);it.p.y=+y.toFixed(2);}it.p.source=it.p.source==="prior"?"hand":it.p.source;draw();});
  const t2=el("text",{x:q[0]*S+8,y:q[1]*S+4,fill:"#fff","font-size":12}); t2.textContent=label; img.appendChild(t2);
 }}
function drag(node,svg,done){node.onpointerdown=e=>{e.preventDefault();const pt=svg.createSVGPoint();
 const at=ev=>{pt.x=ev.clientX;pt.y=ev.clientY;return pt.matrixTransform(svg.getScreenCTM().inverse());};
 const x0=e.clientX,y0=e.clientY;
 const mv=ev=>{const p=at(ev);node.setAttribute("cx",p.x);node.setAttribute("cy",p.y);};
 const up=ev=>{svg.removeEventListener("pointermove",mv);window.removeEventListener("pointerup",up);
  if(Math.hypot(ev.clientX-x0,ev.clientY-y0)>1){const p=at(ev);done(p.x,p.y);}};
 svg.addEventListener("pointermove",mv);window.addEventListener("pointerup",up);};}
async function load(){M=await (await fetch("/moment")).json();H=M.homography&&M.homography.image_to_pitch;Hi=H?inv(H):null;
 S=960/((M.homography&&M.homography.image_size||[1920,1080])[0]);
 document.getElementById("title").textContent=`${M.slug} ${M.clock} (clip ${M.clip_ms} ms)`;draw();}
document.getElementById("fill").onclick=async()=>{M=await (await fetch("/fill",{method:"POST",body:JSON.stringify(M)})).json();draw();};
document.getElementById("save").onclick=async()=>{const r=await fetch("/save",{method:"POST",body:JSON.stringify(M)});
 document.getElementById("msg").textContent=r.ok?"saved "+new Date().toLocaleTimeString():"save failed: "+await r.text();};
load();
</script></body></html>"""


def handler(slug: str, clip_ms: int):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path == "/":
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif self.path == "/moment":
                self._send(200, json.dumps(load(slug, clip_ms)).encode(), "application/json")
            elif self.path == "/frame":
                frame = clip_dir(slug) / load(slug, clip_ms)["frame"]
                kind = "image/png" if frame.suffix == ".png" else "image/jpeg"
                self._send(200, frame.read_bytes(), kind)
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            try:
                doc = self._body()
                if doc.get("slug") != slug or int(doc.get("clip_ms", -1)) != clip_ms:
                    raise ValueError("the page edits one moment only")
                if self.path == "/fill":
                    self._send(200, json.dumps(fill(doc)).encode(), "application/json")
                elif self.path == "/save":
                    save(doc)
                    self._send(200, b"ok", "text/plain")
                else:
                    self._send(404, b"not found", "text/plain")
            except (ValueError, KeyError) as exc:
                self._send(400, str(exc).encode(), "text/plain")

        def log_message(self, *args) -> None:
            return None

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("clip_ms", type=int)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(argv)
    load(args.slug, args.clip_ms)   # fail early on a missing moment file
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(args.slug, args.clip_ms))
    print(f"moment editor on http://127.0.0.1:{args.port}/ (Ctrl-C to stop)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
