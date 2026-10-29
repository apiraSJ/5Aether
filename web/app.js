/* Aether Mark-1 · Frontend interaction layer
 * Demo mode only. Replace the repository below with API calls when integrating.
 */
(() => {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const dateKey = (date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
  const today = new Date();
  today.setHours(0,0,0,0);
  const plusDays = (date, amount) => { const d = new Date(date); d.setDate(d.getDate()+amount); return d; };
  const prettyDate = (value, options={weekday:"short",month:"short",day:"numeric"}) => {
    if (!value) return "No date";
    const d = typeof value === "string" ? new Date(`${value.slice(0,10)}T12:00:00`) : value;
    return Number.isNaN(d.getTime()) ? "No date" : new Intl.DateTimeFormat("en-US", options).format(d);
  };
  const todayKey = dateKey(today);
  const initialTasks = [
    {id:"demo-1",kind:"task",title:"Review project roadmap",description:"Align the next milestones and priorities.",due_date:todayKey,status:"pending",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Planning"},
    {id:"demo-2",kind:"event",title:"Product design sync",description:"Review the latest dashboard concepts.",due_date:null,start_at:`${todayKey}T10:30`,end_at:`${todayKey}T11:00`,status:"pending",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Meeting"},
    {id:"demo-3",kind:"task",title:"Prepare weekly update",description:"Collect progress notes from the team.",due_date:dateKey(plusDays(today,1)),status:"pending",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Work"},
    {id:"demo-4",kind:"task",title:"Organize workspace",description:"Clear out old notes and files.",due_date:dateKey(plusDays(today,-1)),status:"completed",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Personal"},
    {id:"demo-5",kind:"event",title:"Design sprint",description:"Two-day workshop across the team.",due_date:null,start_at:`${dateKey(plusDays(today,-1))}T09:00`,end_at:`${dateKey(plusDays(today,1))}T17:00`,status:"pending",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Workshop"},
    {id:"demo-6",kind:"task",title:"Archived note",description:"Kept for reference only.",due_date:dateKey(plusDays(today,-2)),status:"cancelled",source:"manual",tz:"Asia/Bangkok",all_day:false,internal_status:"confirmed",category:"Archive"}
  ];
  const clone = (item) => ({ ...item });
  const eventEndDate = (item) => {
    const raw = item.end_at || item.start_at || "";
    if (!raw) return "";
    const datePart = raw.slice(0,10);
    // Mirror calendar_query: an end exactly at midnight belongs to the previous day.
    if (raw.includes("T00:00")) return dateKey(plusDays(new Date(`${datePart}T12:00:00`), -1));
    return datePart;
  };
  const eventCoversDate = (item, date) => {
    const start = (item.start_at || "").slice(0,10);
    if (!start) return false;
    return start <= date && date <= eventEndDate(item);
  };
  // Normalize API response item into the frontend item shape used by rendering.
  function normalizeItem(item){
    return {
      id: item.id,
      kind: item.kind,
      title: item.title,
      description: item.description || "",
      due_date: item.due_date || null,
      start_at: item.start_at || null,
      end_at: item.end_at || null,
      status: item.status || "pending",
      internal_status: item.internal_status || "confirmed",
      all_day: !!item.all_day,
      tz: item.tz || "Asia/Bangkok",
      source: item.source || "manual",
      created_at: item.created_at,
      updated_at: item.updated_at,
      category: item.kind === "event" ? "Event" : "Task"
    };
  }

  // API repository: talks to the real FastAPI backend. Only this object needs
  // changing if the API contract evolves; UI rendering stays untouched.
  const apiRepository = {
    async list(){
      const res = await fetch("/api/v1/tasks");
      if (!res.ok) throw new Error(`Failed to load tasks: ${res.status}`);
      const data = await res.json();
      const items = Array.isArray(data.items) ? data.items : [];
      return items.map(normalizeItem);
    },
    async getDay(date){
      const res = await fetch(`/api/v1/calendar/day?date=${encodeURIComponent(date)}`);
      if (!res.ok) throw new Error(`Failed to load day: ${res.status}`);
      const data = await res.json();
      return {
        date: data.date,
        events: (Array.isArray(data.events) ? data.events : []).map(normalizeItem),
        tasks: (Array.isArray(data.tasks) ? data.tasks : []).map(normalizeItem)
      };
    },
    async create(data){
      const payload = {
        kind: data.kind,
        title: data.title,
        description: data.description || "",
        tz: data.tz || "Asia/Bangkok",
        all_day: !!data.all_day,
        source: data.source || "manual"
      };
      // Per API contract: events must not send due_date; tasks must not send start_at/end_at.
      if (data.kind === "event"){
        payload.start_at = data.start_at || null;
        payload.end_at = data.end_at || null;
      } else {
        payload.due_date = data.due_date || null;
      }
      const res = await fetch("/api/v1/tasks",{
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok){
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || `Failed to create task: ${res.status}`);
      }
      return normalizeItem(await res.json());
    },
    async complete(id){
      const res = await fetch(`/api/v1/tasks/${id}/complete`,{ method: "POST" });
      if (!res.ok) throw new Error(`Failed to complete task: ${res.status}`);
      return normalizeItem(await res.json());
    },
    async remove(id){
      const res = await fetch(`/api/v1/tasks/${id}`,{ method: "DELETE" });
      if (!res.ok) throw new Error(`Failed to delete task: ${res.status}`);
    }
  };
  // The UI only talks to `repository`. Swap this line for a different repository later.
  const repository = apiRepository;

  // ContextCal mock repository boundary: swap this object for apiContextCalRepository later.
  const mockContextCalRepository = {
    drafts: {},
    async analyze(text, tz = "Asia/Bangkok"){
      const now = Date.now() / 1000;
      const draftId = `draft_${Date.now().toString(16)}`;
      const textLower = String(text||"").toLowerCase();
      const hasMeeting = /meeting|ประชุม|sync|review|พบคุย/.test(textLower);
      const hasTask = /task|submit|report|finish|complete|ดำเนินการ|ส่งงาน|เขียน/.test(textLower);
      const items = [];
      if(hasMeeting){
        items.push({
          draft_item_id:`ditem_${Date.now().toString(16)}_1`,
          kind:"event",
          title:"Meeting from text",
          description:String(text||""),
          due_date:null,
          start_at:`${todayKey}T09:00`,
          end_at:`${todayKey}T10:00`,
          all_day:false,
          tz,
          confidence:0.85,
          missing_fields:[]
        });
      }
      if(hasTask){
        items.push({
          draft_item_id:`ditem_${Date.now().toString(16)}_2`,
          kind:"task",
          title:"Task from text",
          description:String(text||""),
          due_date:todayKey,
          start_at:null,
          end_at:null,
          all_day:false,
          tz,
          confidence:0.7,
          missing_fields:[]
        });
      }
      if(items.length===0){
        items.push({
          draft_item_id:`ditem_${Date.now().toString(16)}_3`,
          kind:"task",
          title:String(text||"").slice(0,60)||"(untitled)",
          description:String(text||""),
          due_date:todayKey,
          start_at:null,
          end_at:null,
          all_day:false,
          tz,
          confidence:0.5,
          missing_fields:["date"]
        });
      }
      const draft={
        draft_id:draftId,
        source_text:String(text||""),
        content_hash:`hash_${draftId}`,
        items:items.map(item=>({draft_item_id:item.draft_item_id,candidate:item,missing_fields:item.missing_fields,confidence:item.confidence})),
        state:"open",
        tz,
        created_at:now,
        expires_at:now+1800
      };
      this.drafts[draftId]={draft,state:"open",expiresAt:draft.expires_at,createdItemIds:[]};
      return {draft_id:draftId,state:"open",expires_at:draft.expires_at,items};
    },
    async getDraft(draftId){
      const entry=this.drafts[draftId];
      if(!entry) throw new Error("Draft not found");
      if(entry.state==="expired"||Date.now()/1000>entry.expiresAt){
        entry.state="expired";
        throw new Error("Draft expired");
      }
      return entry.draft;
    },
    async confirm(draftId,selections){
      const entry=this.drafts[draftId];
      if(!entry) throw new Error("Draft not found");
      if(entry.state==="expired"||Date.now()/1000>entry.expiresAt){
        entry.state="expired";
        throw new Error("Draft expired");
      }
      if(entry.state==="confirmed"){
        return {draft_id:draftId,committed:true,outcomes:[],created_item_ids:entry.createdItemIds||[]};
      }
      const selMap={};selections.forEach(s=>{selMap[s.draft_item_id]=s;});
      const outcomes=[];const createdIds=[];let committed=true;
      for(const ditem of entry.draft.items){
        const sel=selMap[ditem.draft_item_id];
        if(!sel||!sel.accept) continue;
        const cand=ditem.candidate;const fields=sel.fields||{};
        let missing=[...ditem.missing_fields];
        if((missing.includes("date")||missing.includes("due_date"))&&("due_date" in fields||"start_at" in fields)){
          missing=missing.filter(m=>m!=="date"&&m!=="due_date");
        }
        if(missing.includes("time")&&"start_at" in fields) missing=missing.filter(m=>m!=="time");
        if(missing.includes("tz")&&"tz" in fields) missing=missing.filter(m=>m!=="tz");
        if(missing.length>0){
          outcomes.push({draft_item_id:ditem.draft_item_id,ok:false,item_id:null,error:`missing:${missing.join(",")}`});
          committed=false;
          continue;
        }
        const data={kind:cand.kind,title:fields.title||cand.title,description:fields.description||cand.description,due_date:fields.due_date||cand.due_date,start_at:fields.start_at||cand.start_at,end_at:fields.end_at||cand.end_at,all_day:fields.all_day!==undefined?fields.all_day:cand.all_day,tz:fields.tz||cand.tz||entry.draft.tz,source:"extraction"};
        const created=await repository.create(data);
        createdIds.push(created.id);
        outcomes.push({draft_item_id:ditem.draft_item_id,ok:true,item_id:created.id,error:null});
      }
      if(committed){
        entry.state="confirmed";
        entry.createdItemIds=createdIds;
      }
      return {draft_id:draftId,committed,outcomes,created_item_ids:createdIds};
    },
    async discard(draftId){
      const entry=this.drafts[draftId];
      if(!entry) return false;
      entry.state="discarded";
      return true;
    }
  };
  // API ContextCal repository: talks to the real FastAPI backend.
  const apiContextCalRepository = {
    drafts: {},
    async analyze(text, tz = "Asia/Bangkok"){
      const res = await fetch("/api/v1/contextcal/analyze",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({text, tz})
      });
      if(!res.ok){
        const err = await res.json().catch(()=>({}));
        throw new Error(err.message || `Failed to analyze: ${res.status}`);
      }
      const data = await res.json();
      this.drafts[data.draft_id] = {draft:data, state:data.state, expiresAt:data.expires_at, createdItemIds:[]};
      return data;
    },
    async getDraft(draftId){
      const entry = this.drafts[draftId];
      if(!entry) throw new Error("Draft not found");
      // Refresh from API if expired locally
      try{
        const res = await fetch(`/api/v1/contextcal/drafts/${draftId}`);
        if(res.ok){
          const data = await res.json();
          entry.draft = data;
          entry.state = data.state;
          entry.expiresAt = data.expires_at;
        }
      }catch(e){}
      return entry.draft;
    },
    async confirm(draftId, selections){
      const res = await fetch(`/api/v1/contextcal/drafts/${draftId}/confirm`,{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({selections})
      });
      if(!res.ok){
        const err = await res.json().catch(()=>({}));
        throw new Error(err.message || `Failed to confirm: ${res.status}`);
      }
      const data = await res.json();
      if(this.drafts[draftId]){
        this.drafts[draftId].state = data.committed ? "confirmed" : this.drafts[draftId].state;
        this.drafts[draftId].createdItemIds = data.created_item_ids || [];
      }
      return data;
    },
    async discard(draftId){
      const res = await fetch(`/api/v1/contextcal/drafts/${draftId}`,{method:"DELETE"});
      if(!res.ok) return false;
      delete this.drafts[draftId];
      return true;
    }
  };
  const contextcalRepository = apiContextCalRepository;
  let contextcalDraft = null; // { draft, entry }
  let contextcalSelections = {}; // draft_item_id -> { accept, fields }
  let contextcalEditingId = null; // draft_item_id being inline-edited
  let items = [];
  let currentPage = "tasks";
  let calendarAnchor = new Date(today);
  let selectedDate = todayKey;
  let calendarView = "month";
  let toastTimer = null;
  let dayRequestId = 0;

  const escapeHtml = (value="") => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const showToast = (message) => {
    const toast=$("#toast");toast.textContent=message;toast.classList.add("show");
    clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove("show"),2600);
  };
  const syncBodyLock = () => {
    const open = !$("#task-modal").hidden || !$("#detail-modal").hidden;
    document.body.style.overflow = open ? "hidden" : "";
  };
  const itemDate = (item) => item.kind === "event"
    ? (item.start_at ? item.start_at.slice(0,10) : "")
    : (item.due_date || (item.start_at ? item.start_at.slice(0,10) : ""));
  const itemTime = (item) => {
    if (item.start_at) {
      const match = String(item.start_at).match(/T(\d{2}):(\d{2})/);
      if (match) return `${match[1]}:${match[2]}`;
      return prettyDate(item.start_at, {month:"short",day:"numeric"});
    }
    if (item.due_date) return prettyDate(item.due_date,{month:"short",day:"numeric"});
    return "No date";
  };
  const statusLabel = (item) => {
    if (item.status === "cancelled") return "Cancelled";
    if (item.kind === "event") return "Event";
    return item.status === "completed" ? "Completed" : "Pending";
  };
  const statusClass = (item) => item.status === "completed"
    ? "status-completed"
    : item.status === "cancelled"
      ? "status-cancelled"
      : item.kind === "event"
        ? "status-event"
        : "status-pending";
  const formatDateTime = (value) => value ? String(value).replace("T"," ") : "—";
  const syncCounts = () => {
    const pending = items.filter(x => x.status === "pending");
    const completed = items.filter(x => x.status === "completed");
    $("#nav-task-count").textContent = pending.length;
    $("#stat-all").textContent = items.length;
    $("#stat-progress").textContent = pending.length;
    $("#stat-completed").textContent = completed.length;
    $("#stat-today").textContent = pending.filter(x => x.kind === "event" ? eventCoversDate(x, todayKey) : itemDate(x) === todayKey).length;
  };

  function renderTasks(){
    const query=$("#task-search").value.trim().toLowerCase();
    const filter=$("#task-filter").value;
    const visible=items.filter(item=>{
      const matchesQuery=[item.title,item.description,item.category].some(v=>String(v||"").toLowerCase().includes(query));
      const matchesFilter=filter==="all"||item.status===filter;
      return matchesQuery&&matchesFilter;
    });
    const list=$("#task-list");list.replaceChildren();
    visible.forEach(item=>{
      const row=document.createElement("article");
      row.className=`task-row${item.status==="completed"?" is-complete":""}${item.status==="cancelled"?" is-cancelled":""}`;
      const main=document.createElement("div");main.className="task-main";
      const check=document.createElement("button");
      check.className=`task-check${item.status==="completed"?" checked":""}`;
      check.type="button";
      check.disabled=item.status!=="pending";
      check.setAttribute("aria-label",item.status==="pending"?"Mark task completed":statusLabel(item));
      check.textContent=item.status==="completed"?"✓":"";
      check.addEventListener("click",async()=>{
        if(item.status!=="pending") return;
        try{await repository.complete(item.id);await refresh();showToast("Task completed");}
        catch(error){showToast(`Could not complete task: ${error.message}`);}
      });
      const copy=document.createElement("div");copy.className="task-copy";
      const title=document.createElement("span");title.className="task-title";title.textContent=item.title;
      const desc=document.createElement("span");desc.className="task-description";desc.textContent=item.description||"No description";
      copy.append(title,desc);main.append(check,copy);
      const meta=document.createElement("div");meta.className="task-meta";meta.innerHTML=`<strong>${item.kind==="event"?"SCHEDULE":"DUE DATE"}</strong>${escapeHtml(itemTime(item))}`;
      const badge=document.createElement("span");badge.className=`status-badge ${statusClass(item)}`;badge.textContent=statusLabel(item);
      const menu=document.createElement("button");menu.className="task-menu";menu.type="button";menu.textContent="···";menu.setAttribute("aria-label",`Delete ${item.title}`);
      menu.addEventListener("click",async()=>{
        if(!window.confirm(`Delete "${item.title}" from this demo?`)) return;
        try{await repository.remove(item.id);await refresh();showToast("Item deleted from demo");}
        catch(error){showToast(`Could not delete item: ${error.message}`);}
      });
      row.append(main,meta,badge,menu);list.append(row);
    });
    $("#task-empty").hidden=visible.length!==0;
    syncCounts();
  }

  function renderCalendar(){
    const title=$("#calendar-title");
    title.textContent=calendarView==="day"?prettyDate(selectedDate,{weekday:"long",month:"long",day:"numeric",year:"numeric"}):calendarView==="week"?`Week of ${prettyDate(getWeekStart(calendarAnchor),{month:"short",day:"numeric"})}`:new Intl.DateTimeFormat("en-US",{month:"long",year:"numeric"}).format(calendarAnchor);
    const grid=$("#calendar-grid");
    grid.classList.toggle("week-mode",calendarView==="week");
    grid.classList.toggle("day-mode",calendarView==="day");
    const weekdayBar=$(".calendar-weekdays");
    weekdayBar.replaceChildren();
    if(calendarView==="day"){
      const dayLabel=document.createElement("span");
      dayLabel.textContent=prettyDate(selectedDate,{weekday:"long"});
      weekdayBar.append(dayLabel);
      weekdayBar.style.gridTemplateColumns="minmax(0,1fr)";
    }else{
      ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].forEach(label=>{const span=document.createElement("span");span.textContent=label;weekdayBar.append(span);});
      weekdayBar.style.gridTemplateColumns="repeat(7,minmax(0,1fr))";
    }
    grid.replaceChildren();
    if(calendarView==="month"){
      const first=new Date(calendarAnchor.getFullYear(),calendarAnchor.getMonth(),1);
      const offset=(first.getDay()+6)%7;
      const start=plusDays(first,-offset);
      for(let i=0;i<42;i++)addCalendarCell(plusDays(start,i),grid,calendarAnchor.getMonth());
    } else if(calendarView==="week"){
      const start=getWeekStart(calendarAnchor);
      for(let i=0;i<7;i++)addCalendarCell(plusDays(start,i),grid,calendarAnchor.getMonth(),true);
    } else {
      addCalendarCell(new Date(`${selectedDate}T12:00:00`),grid,calendarAnchor.getMonth(),true);
    }
    loadDay(selectedDate);
  }
  function getWeekStart(date){const d=new Date(date);d.setHours(0,0,0,0);const day=(d.getDay()+6)%7;d.setDate(d.getDate()-day);return d;}
  function addCalendarCell(date,grid,month,compact=false){
    const key=dateKey(date);
    const cell=document.createElement("div");
    cell.className="calendar-cell";
    cell.tabIndex=0;
    cell.setAttribute("role","button");
    cell.setAttribute("aria-label",prettyDate(date,{weekday:"long",month:"long",day:"numeric",year:"numeric"}));
    cell.setAttribute("aria-pressed",String(key===selectedDate));
    if(date.getMonth()!==month&&calendarView==="month")cell.classList.add("outside-month");
    if(key===todayKey)cell.classList.add("today");
    if(key===selectedDate)cell.classList.add("selected");
    const number=document.createElement("div");number.className="calendar-day-number";number.textContent=date.getDate();cell.append(number);
    const dayItems=items.filter(item=>item.kind==="event"?eventCoversDate(item,key):itemDate(item)===key);
    dayItems.sort((a,b)=>{
      if(a.kind!==b.kind) return a.kind==="event"?-1:1;
      return (a.start_at||a.due_date||"").localeCompare(b.start_at||b.due_date||"");
    });
    const max=compact?8:2;
    dayItems.slice(0,max).forEach(item=>{
      const ev=document.createElement("button");ev.type="button";ev.className="calendar-event";
      ev.classList.add(item.status==="cancelled"?"event-grey":item.kind==="event"?"event-blue":item.status==="completed"?"event-green":"event-amber");
      ev.textContent=item.title;ev.title=item.title;
      ev.addEventListener("click",e=>{e.stopPropagation();selectDate(key);openDetail(item);});
      cell.append(ev);
    });
    if(dayItems.length>max){const more=document.createElement("div");more.className="more-events";more.textContent=`+${dayItems.length-max} more`;cell.append(more);}
    cell.addEventListener("click",()=>selectDate(key));
    cell.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();selectDate(key);}});
    grid.append(cell);
  }
  function selectDate(date){
    selectedDate=date;
    calendarAnchor=new Date(`${date}T12:00:00`);
    renderCalendar();
  }

  async function loadDay(date=selectedDate){
    const requestId=++dayRequestId;
    $("#selected-date-label").textContent=prettyDate(date,{weekday:"long",month:"long",day:"numeric"});
    $("#selected-day-count").textContent="Loading…";
    $("#day-loading").hidden=false;
    $("#day-error").hidden=true;
    $("#day-empty").hidden=true;
    $("#selected-events").replaceChildren();
    try{
      const data=await repository.getDay(date);
      if(requestId!==dayRequestId) return;
      renderDay(data);
    }catch(error){
      if(requestId!==dayRequestId) return;
      $("#selected-day-count").textContent="Could not load";
      $("#day-error-message").textContent=error.message||"Could not load this day.";
      $("#day-error").hidden=false;
    }finally{
      if(requestId===dayRequestId) $("#day-loading").hidden=true;
    }
  }
  function renderDay(data){
    const events=Array.isArray(data.events)?data.events:[];
    const tasks=Array.isArray(data.tasks)?data.tasks:[];
    const all=[...events,...tasks];
    $("#selected-day-count").textContent=`${all.length} item${all.length===1?"":"s"}`;
    const wrap=$("#selected-events");wrap.replaceChildren();
    $("#day-empty").hidden=all.length!==0;
    all.forEach(item=>{
      const card=document.createElement("button");
      card.type="button";card.className="selected-event day-item";
      const title=document.createElement("strong");title.textContent=item.title||"(untitled)";
      const detail=document.createElement("span");detail.textContent=`${item.kind==="event"?"Event":"Task"} · ${itemTime(item)}`;
      const status=document.createElement("span");status.className=`status-badge ${statusClass(item)}`;status.textContent=statusLabel(item);
      card.append(title,detail,status);
      card.addEventListener("click",()=>openDetail(item));
      wrap.append(card);
    });
  }

  function openDetail(item){
    $("#detail-title").textContent=item.title||"Item details";
    $("#detail-subtitle").textContent=item.kind==="event"
      ? `Event · ${formatDateTime(item.start_at)}`
      : `Task · ${statusLabel(item)}`;
    const rows=[
      ["Kind",item.kind==="event"?"Event":"Task"],
      ["Status",statusLabel(item)],
      ["Due date",item.due_date||"—"],
      ["Start",formatDateTime(item.start_at)],
      ["End",formatDateTime(item.end_at)],
      ["All day",item.all_day?"Yes":"No"],
      ["Timezone",item.tz||"Asia/Bangkok"],
      ["Description",item.description||"—"],
      ["Source",item.source||"manual"],
      ["ID",item.id||"—"]
    ];
    const grid=$("#detail-grid");grid.replaceChildren();
    rows.forEach(([label,value])=>{
      const row=document.createElement("div");
      row.className=`detail-row${label==="Description"?" full":""}`;
      const key=document.createElement("span");key.textContent=label;
      const val=document.createElement("strong");val.textContent=value;
      if(label==="ID") val.classList.add("detail-id");
      row.append(key,val);grid.append(row);
    });
    $("#detail-modal").hidden=false;
    syncBodyLock();
  }
  function closeDetail(){
    $("#detail-modal").hidden=true;
    syncBodyLock();
  }

  function setPage(page){
    currentPage=page;
    $("#tasks-page").hidden=page!=="tasks";
    $("#calendar-page").hidden=page!=="calendar";
    $("#contextcal-page").hidden=page!=="contextcal";
    $$(".nav-item").forEach(btn=>btn.classList.toggle("active",btn.dataset.page===page));
    $("#breadcrumb-current").textContent=page==="tasks"?"Tasks":page==="calendar"?"Calendar":"ContextCal";
    $("#sidebar").classList.remove("open");
    if(page==="calendar")renderCalendar();
    if(page==="contextcal")renderContextCalPage();
  }

  // ---------- ContextCal ----------
  function renderContextCalPage(){
    $("#cc-analyze").disabled=false;
    $("#cc-text").disabled=false;
    $("#cc-tz").disabled=false;
    $("#cc-loading").hidden=true;
    $("#cc-error").hidden=true;
    $("#cc-draft-card").hidden=true;
    $("#cc-outcomes").replaceChildren();
    contextcalDraft=null;contextcalSelections={};contextcalEditingId=null;
  }
  function renderDraft(){
    if(!contextcalDraft){$("#cc-draft-card").hidden=true;return;}
    const {draft}=contextcalDraft;
    $("#cc-draft-card").hidden=false;
    $("#cc-draft-id").textContent=`ID: ${draft.draft_id}`;
    const expires=new Date(draft.expires_at*1000);
    $("#cc-expires").textContent=`Expires: ${prettyDate(expires,{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"})}`;
    const stateBadge=$("#cc-draft-card .cc-state-badge");
    stateBadge.textContent=draft.state.charAt(0).toUpperCase()+draft.state.slice(1);
    stateBadge.className=`cc-badge cc-state-badge ${draft.state==="open"?"":draft.state==="confirmed"?"cc-state-badge":"cc-state-badge"}`;
    renderContextCalItems();
  }
  function normalizeForInput(value, kind){
    if(value===null||value===undefined) return "";
    const s=String(value).trim();
    if(!s) return "";
    if(kind==="date") return s.slice(0,10);
    if(kind==="datetime-local") return s.slice(0,16);
    return s;
  }
  function originalFieldValue(cand, key){
    if(key==="due_date") return cand.due_date||"";
    if(key==="start_at") return cand.start_at||"";
    if(key==="end_at") return cand.end_at||"";
    if(key==="tz") return cand.tz||"";
    if(key==="title") return cand.title||"";
    if(key==="description") return cand.description||"";
    return cand[key]||"";
  }
  function renderContextCalItems(){
    if(!contextcalDraft){$("#cc-items").replaceChildren();return;}
    const wrap=$("#cc-items");wrap.replaceChildren();
    const now=Date.now()/1000;
    const expired=contextcalDraft.entry.state==="expired"||now>contextcalDraft.entry.expiresAt;
    contextcalDraft.entry.draft.items.forEach(ditem=>{
      const cand=ditem.candidate;
      const sel=contextcalSelections[ditem.draft_item_id]||{accept:true,fields:{}};
      const fields=sel.fields||{};
      const editedKeys=Object.keys(fields).filter(k=>fields[k]!==undefined&&fields[k]!==null&&String(fields[k]).trim()!=="");
      const isEdited=editedKeys.length>0;
      const card=document.createElement("div");card.className="cc-item";
      const header=document.createElement("div");header.className="cc-item-header";
      const accept=document.createElement("input");accept.type="checkbox";accept.checked=!!sel.accept;
      accept.setAttribute("aria-label",`Accept ${cand.title}`);
      accept.addEventListener("change",()=>{
        const cur=contextcalSelections[ditem.draft_item_id]||sel;
        contextcalSelections[ditem.draft_item_id]={accept:accept.checked,fields:cur.fields||{}};
      });
      const kind=document.createElement("span");kind.className="cc-item-kind";kind.textContent=cand.kind==="event"?"Event":"Task";
      const conf=document.createElement("span");conf.className="cc-confidence";conf.textContent=`${Math.round((cand.confidence||0)*100)}%`;
      header.append(accept,kind,conf);
      const title=document.createElement("h3");title.className="cc-item-title";
      const displayTitle=fields.title||cand.title||"(untitled)";
      title.textContent=displayTitle;
      if(isEdited){
        const badge=document.createElement("span");badge.className="cc-edited-badge";badge.textContent="Edited";
        title.append(badge);
      }
      const desc=document.createElement("p");desc.className="cc-item-desc";desc.textContent=fields.description||cand.description||"—";
      const fieldsWrap=document.createElement("div");fieldsWrap.className="cc-item-fields";
      const missing=document.createElement("div");
      if(ditem.missing_fields&&ditem.missing_fields.length){
        missing.textContent=`Missing: ${ditem.missing_fields.join(", ")}`;
        missing.className="cc-missing-chip";
      }else{missing.hidden=true;}

      // Determine which fields to show based on kind
      const fieldDefs=[];
      if(cand.kind==="task"){
        fieldDefs.push({label:"Due date",key:"due_date",type:"date",placeholder:"YYYY-MM-DD"});
      }
      if(cand.kind==="event"){
        fieldDefs.push({label:"Start",key:"start_at",type:"datetime-local",placeholder:""});
        fieldDefs.push({label:"End",key:"end_at",type:"datetime-local",placeholder:""});
      }
      fieldDefs.push({label:"Timezone",key:"tz",type:"text",placeholder:"Asia/Bangkok"});
      // Title editable too (optional, but useful)
      fieldDefs.unshift({label:"Title",key:"title",type:"text",placeholder:"Title"});

      fieldDefs.forEach(fd=>{
        const f=document.createElement("div");f.className="cc-item-field";
        const l=document.createElement("label");l.textContent=fd.label;f.append(l);
        const i=document.createElement("input");i.type=fd.type;i.placeholder=fd.placeholder||"";
        const origVal=originalFieldValue(cand,fd.key);
        const editedVal=fields[fd.key];
        const shownVal = (editedVal!==undefined&&editedVal!==null&&String(editedVal).trim()!=="")
          ? editedVal
          : origVal;
        i.value=normalizeForInput(shownVal, fd.type);
        // mark edited
        const isFieldEdited = editedVal!==undefined&&editedVal!==null&&String(editedVal).trim()!=="" && String(editedVal).trim()!==String(origVal).trim();
        if(isFieldEdited){ i.style.borderColor="#b77b18"; i.style.background="#fffaf0"; }
        i.addEventListener("input",()=>{
          const v=i.value.trim();
          const curSel=contextcalSelections[ditem.draft_item_id]||{accept:true,fields:{}};
          const newFields={...(curSel.fields||{})};
          if(v==="" || v===String(origVal).trim().slice(0, (fd.type==="datetime-local"?16:10))){
            // reverted to original (or empty) -> remove override
            delete newFields[fd.key];
          } else {
            newFields[fd.key]=v;
          }
          const curSel2=contextcalSelections[ditem.draft_item_id]||sel;
          contextcalSelections[ditem.draft_item_id]={accept:curSel2.accept,fields:newFields};
        });
        // Reset button per field
        const resetBtn=document.createElement("button");resetBtn.type="button";
        resetBtn.textContent="Reset";resetBtn.className="button button-light";
        resetBtn.style.cssText="font-size:9px;padding:2px 6px;margin-top:2px;align-self:flex-start";
        resetBtn.addEventListener("click",()=>{
          const curSel=contextcalSelections[ditem.draft_item_id]||{accept:true,fields:{}};
          const newFields={...(curSel.fields||{})};
          delete newFields[fd.key];
          const curSel2=contextcalSelections[ditem.draft_item_id]||sel;
          contextcalSelections[ditem.draft_item_id]={accept:curSel2.accept,fields:newFields};
          renderDraft();
        });
        f.append(i,resetBtn);fieldsWrap.append(f);
      });

      // Per-item reset all edits
      const actions=document.createElement("div");actions.style.display="flex";actions.style.gap="8px";actions.style.marginTop="8px";actions.style.flexWrap="wrap";
      const resetAllBtn=document.createElement("button");resetAllBtn.type="button";resetAllBtn.className="button button-light";resetAllBtn.textContent="Reset all edits";
      resetAllBtn.addEventListener("click",()=>{
        const cur=contextcalSelections[ditem.draft_item_id]||sel;
        contextcalSelections[ditem.draft_item_id]={accept:cur.accept,fields:{}};
        renderDraft();
      });
      const rejectBtn=document.createElement("button");rejectBtn.type="button";rejectBtn.className="button button-light";rejectBtn.textContent="Reject";
      rejectBtn.addEventListener("click",()=>{
        contextcalSelections[ditem.draft_item_id]={accept:false,fields:sel.fields};
        renderDraft();
      });
      actions.append(resetAllBtn,rejectBtn);
      card.append(header,title,desc,fieldsWrap,missing,actions);
      wrap.append(card);
    });
  }
  function renderOutcomes(result){
    const wrap=$("#cc-outcomes");wrap.replaceChildren();
    if(!result.outcomes||result.outcomes.length===0){
      if(result.committed){
        const empty=document.createElement("div");empty.className="cc-outcome ok";
        empty.innerHTML=`<span class="cc-outcome-kind">Confirmed</span><div class="cc-outcome-item">All selected items saved.</div><span class="cc-outcome-id">IDs: ${(result.created_item_ids||[]).join(", ")||"—"}</span>`;
        wrap.append(empty);
      }
      return;
    }
    result.outcomes.forEach(o=>{
      const div=document.createElement("div");div.className=`cc-outcome ${o.ok?"ok":"error"}`;
      div.innerHTML=`<span class="cc-outcome-kind">${o.ok?"Created":"Rejected"}</span><div class="cc-outcome-item">${o.item_id||(o.error||"")}</div><span class="cc-outcome-id">${o.draft_item_id}</span>`;
      wrap.append(div);
    });
  }
  function openModal({kind="task",date=todayKey}={}){
    const targetDate=/^\d{4}-\d{2}-\d{2}$/.test(date)?date:todayKey;
    $("#create-form").reset();
    $("#form-kind").value=kind;
    $("#form-due").value=targetDate;
    const start=new Date(`${targetDate}T09:00:00`);
    const end=new Date(start.getTime()+30*60000);
    const toLocal=(d)=>`${dateKey(d)}T${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
    $("#form-start").value=toLocal(start);
    $("#form-end").value=toLocal(end);
    updateKindFields();
    $("#modal-title").textContent=kind==="event"?"Create an event":"Create a task";
    $("#task-modal").hidden=false;
    syncBodyLock();
    $("#form-title").focus();
  }
  function closeModal(){$("#task-modal").hidden=true;syncBodyLock();}
  function updateKindFields(){
    const isEvent=$("#form-kind").value==="event";
    $("#due-field").hidden=isEvent;$("#start-field").hidden=!isEvent;$("#end-field").hidden=!isEvent;
    $("#modal-title").textContent=isEvent?"Create an event":"Create a task";
  }
  async function refresh(){
    try{
      items=await repository.list();
    }catch(error){
      items=[];
      showToast(`Could not load items: ${error.message}`);
    }
    renderTasks();
    if(currentPage==="calendar")renderCalendar();
  }

  $("#open-create").addEventListener("click",()=>openModal({kind:"task",date:todayKey}));
  $("#calendar-add").addEventListener("click",()=>openModal({kind:"event",date:selectedDate}));
  $("#day-add-task").addEventListener("click",()=>openModal({kind:"task",date:selectedDate}));
  $("#day-empty-add").addEventListener("click",()=>openModal({kind:"task",date:selectedDate}));
  $("#day-retry").addEventListener("click",()=>loadDay(selectedDate));
  $("#day-open-view").addEventListener("click",()=>{
    calendarView="day";
    $$(".view-button").forEach(b=>b.classList.toggle("active",b.dataset.view==="day"));
    calendarAnchor=new Date(`${selectedDate}T12:00:00`);
    renderCalendar();
  });
  $("#close-modal").addEventListener("click",closeModal);$("#cancel-modal").addEventListener("click",closeModal);
  $("#task-modal").addEventListener("click",e=>{if(e.target===$("#task-modal"))closeModal();});
  $("#close-detail").addEventListener("click",closeDetail);
  $("#close-detail-footer").addEventListener("click",closeDetail);
  $("#detail-modal").addEventListener("click",e=>{if(e.target===$("#detail-modal"))closeDetail();});
  document.addEventListener("keydown",e=>{
    if(e.key!=="Escape") return;
    if(!$("#detail-modal").hidden)closeDetail();
    else if(!$("#task-modal").hidden)closeModal();
  });
  $("#form-kind").addEventListener("change",updateKindFields);
  $("#create-form").addEventListener("submit",async e=>{
    e.preventDefault();
    const kind=$("#form-kind").value,title=$("#form-title").value.trim();
    if(!title){$("#form-title").focus();return;}
    const data={kind,title,description:$("#form-description").value.trim(),tz:"Asia/Bangkok",all_day:false};
    if(kind==="event"){
      data.start_at=$("#form-start").value;data.end_at=$("#form-end").value;
      if(!data.start_at||!data.end_at){showToast("Please add start and end times");return;}
      if(new Date(data.end_at)<new Date(data.start_at)){showToast("End time must be after start time");return;}
    } else data.due_date=$("#form-due").value||null;
    try{
      await repository.create(data);
      if(kind==="event"){
        selectedDate=data.start_at.slice(0,10);
        calendarAnchor=new Date(`${selectedDate}T12:00:00`);
      }
      await refresh();closeModal();showToast(kind==="event"?"Event added to demo calendar":"Task added to demo list");
    }catch(error){
      showToast(`Could not save: ${error.message}`);
    }
  });
  $$(".nav-item").forEach(btn=>btn.addEventListener("click",()=>setPage(btn.dataset.page)));
  $("#mobile-menu").addEventListener("click",()=>$("#sidebar").classList.toggle("open"));
  $("#task-search").addEventListener("input",renderTasks);$("#task-filter").addEventListener("change",renderTasks);
  $("#cal-prev").addEventListener("click",()=>{calendarAnchor=calendarView==="week"?plusDays(calendarAnchor,-7):calendarView==="day"?plusDays(calendarAnchor,-1):new Date(calendarAnchor.getFullYear(),calendarAnchor.getMonth()-1,1);selectedDate=dateKey(calendarAnchor);renderCalendar();});
  $("#cal-next").addEventListener("click",()=>{calendarAnchor=calendarView==="week"?plusDays(calendarAnchor,7):calendarView==="day"?plusDays(calendarAnchor,1):new Date(calendarAnchor.getFullYear(),calendarAnchor.getMonth()+1,1);selectedDate=dateKey(calendarAnchor);renderCalendar();});
  $("#cal-today").addEventListener("click",()=>{calendarAnchor=new Date(today);selectedDate=todayKey;renderCalendar();});
  $$(".view-button").forEach(btn=>btn.addEventListener("click",()=>{calendarView=btn.dataset.view;$$(".view-button").forEach(b=>b.classList.toggle("active",b===btn));calendarAnchor=new Date(`${selectedDate}T12:00:00`);renderCalendar();}));
  $("#today-pill").textContent=prettyDate(today,{month:"short",day:"numeric",year:"numeric"});
  // ContextCal wiring
  $("#cc-analyze").addEventListener("click",async()=>{
    const text=$("#cc-text").value.trim();
    if(!text){$("#cc-text").focus();return;}
    $("#cc-analyze").disabled=true;$("#cc-text").disabled=true;$("#cc-tz").disabled=true;
    $("#cc-loading").hidden=false;$("#cc-error").hidden=true;
    try{
      const tz=$("#cc-tz").value;
      const data=await contextcalRepository.analyze(text,tz);
      contextcalDraft={draft:data,entry:contextcalRepository.drafts[data.draft_id]};
      contextcalSelections={};
      data.items.forEach(ditem=>{
        contextcalSelections[ditem.draft_item_id]={accept:true,fields:{}};
      });
      renderDraft();
      showToast("Draft created — review before confirming");
    }catch(error){
      $("#cc-error-message").textContent=error.message||"Could not analyze.";
      $("#cc-error").hidden=false;
    }finally{
      $("#cc-loading").hidden=true;
    }
  });
  $("#cc-discard").addEventListener("click",async()=>{
    if(!contextcalDraft) return;
    if(!window.confirm("Discard this draft? Items already confirmed will not be removed.")) return;
    try{
      await contextcalRepository.discard(contextcalDraft.entry.draft.draft_id);
      renderContextCalPage();
      showToast("Draft discarded");
    }catch(error){
      showToast(`Could not discard: ${error.message}`);
    }
  });
  $("#cc-confirm").addEventListener("click",async()=>{
    if(!contextcalDraft){showToast("No draft to confirm");return;}
    const selections=Object.entries(contextcalSelections).map(([draft_item_id,s])=>{
      const ditem=contextcalDraft.entry.draft.items.find(x=>x.draft_item_id===draft_item_id);
      const cand=ditem?ditem.candidate:{};
      const orig={
        title:cand.title||"",
        description:cand.description||"",
        due_date:cand.due_date||"",
        start_at:cand.start_at||"",
        end_at:cand.end_at||"",
        tz:cand.tz||"",
      };
      const raw=s.fields||{};
      const cleaned={};
      Object.keys(raw).forEach(k=>{
        const v=raw[k];
        if(v===undefined||v===null) return;
        const str=String(v).trim();
        if(str==="") return;
        // normalize datetime-local (no seconds) -> full ISO seconds
        let norm=str;
        if((k==="start_at"||k==="end_at") && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(str)){
          norm=str+":00";
        }
        // only send if actually changed from original
        const origNorm = (k==="start_at"||k==="end_at") ? String(orig[k]||"").slice(0,16) : String(orig[k]||"").trim();
        if(norm===origNorm) return; // unchanged -> skip
        cleaned[k]=norm;
      });
      return {draft_item_id,accept:s.accept,fields:cleaned};
    });
    if(!selections.some(s=>s.accept)){showToast("Select at least one item");return;}
    $("#cc-confirm").disabled=true;$("#cc-discard").disabled=true;
    $("#cc-confirm-loading").hidden=false;$("#cc-confirm-error").hidden=true;
    try{
      const result=await contextcalRepository.confirm(contextcalDraft.entry.draft.draft_id,selections);
      renderOutcomes(result);
      if(result.committed){
        await refresh();
        showToast(`Confirmed — ${result.created_item_ids.length} item${result.created_item_ids.length===1?"":"s"} created`);
        if(currentPage==="contextcal")renderDraft();
      }else{
        showToast("Some items could not be confirmed (see outcomes)");
      }
    }catch(error){
      $("#cc-confirm-error-message").textContent=error.message||"Could not confirm.";
      $("#cc-confirm-error").hidden=false;
    }finally{
      $("#cc-confirm-loading").hidden=true;
      $("#cc-confirm").disabled=false;$("#cc-discard").disabled=false;
    }
  });
  refresh();
})();
