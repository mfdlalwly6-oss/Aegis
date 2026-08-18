const API="/api/v1";
const state={decisions:[]};
const $=s=>document.querySelector(s);
const el=(t,a={},...kids)=>{const n=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==="class")n.className=v;else if(k.startsWith("on"))n.addEventListener(k.slice(2),v);else n.setAttribute(k,v)}for(const c of kids.flat())if(c!=null)n.appendChild(typeof c==="string"?document.createTextNode(c):c);return n};

const dt=iso=>{
  if(!iso)return "-";
  const d=new Date(iso);
  if(Number.isNaN(d.getTime()))return "-";
  return d.toLocaleString("ar-SA",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
};

function toast(m,t="info"){const d=el("div",{class:"toast "+t},m);document.body.appendChild(d);setTimeout(()=>d.remove(),3000)}

async function load(){
  try{
    const r=await fetch(API+"/decisions/recent?limit=50",{cache:"no-store"});
    const data=await r.json();
    state.decisions=Array.isArray(data)?data:(data.value||[]);
  }catch(e){state.decisions=[]}
}

function renderTable(){
  return el("div",{class:"card"},
    state.decisions.length===0
    ?el("div",{style:"text-align:center;color:var(--muted);padding:40px"},"لا توجد قرارات بعد. جرّب تحويلاً من المحفظة.")
    :el("table",{},
      el("thead",{},el("tr",{},
        el("th",{},"الوقت"),
        el("th",{},"المعرّف"),
        el("th",{},"المؤسسة"),
        el("th",{},"القرار"),
        el("th",{},"المخاطر"),
        el("th",{},"AI"),
        el("th",{},"التفسير")
      )),
      el("tbody",{},...state.decisions.map(d=>
        el("tr",{},
          el("td",{style:"font-size:11px;white-space:nowrap"},dt(d.ts||d.timestamp||d.created_at)),
          el("td",{},el("code",{style:"font-size:11px"},(d.tx_id||"").slice(0,14))),
          el("td",{style:"font-size:12px"},d.tenant_name||d.tenant_id||"-"),
          el("td",{},el("span",{class:"badge "+d.decision},d.decision)),
          el("td",{style:"font-weight:700"},((d.risk_score||0)*100).toFixed(0)+"%"),
          el("td",{style:"font-size:11px;color:var(--muted)"},d.ai_model||d.components?.ai_agent?.model||"-"),
          el("td",{style:"font-size:11px;max-width:280px;color:var(--muted)"},d.reasoning_ar||"")
        )
      ))
    )
  );
}

function render(){
  const root=$("#app");root.innerHTML="";
  root.appendChild(el("div",{},
    el("div",{class:"top-nav"},
      el("div",{},
        el("span",{style:"font-size:1.7rem"},"🛡️ "),
        el("strong",{style:"font-size:1.2rem;color:var(--accent)"},"AEGIS — لوحة تحقيقات الاحتيال")
      ),
      el("div",{style:"display:flex;gap:10px"},
        el("a",{href:"/admin/",class:"btn"},"👑 المالك"),
        el("a",{href:"/merchant/",class:"btn"},"🏦 المؤسسة"),
        el("a",{href:"/",class:"btn"},"💳 المحفظة"),
        el("button",{class:"btn primary",onclick:async()=>{await load();render();toast("تم التحديث","success")}},"🔄")
      )
    ),
    el("main",{style:"padding:24px;max-width:1400px;margin:0 auto"},
      el("div",{class:"hero"},
        el("h1",{style:"font-size:1.6rem;font-weight:900"},"🔍 مراقبة القرارات الحيّة"),
        el("p",{style:"color:var(--muted);margin-top:6px"},"جميع قرارات AEGIS عبر كل المؤسسات المرتبطة (Multi-Tenant)")
      ),
      renderTable()
    )
  ));
}

(async()=>{await load();render();setInterval(async()=>{await load();render()},8000)})();