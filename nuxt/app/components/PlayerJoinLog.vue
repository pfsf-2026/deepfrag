<script setup>
// Server join log (2026-11-09, Peter): everyone who joins our servers, by IP and nick, with
// aliasing flagged. Owner only — the API answers 403 to everyone but Peter's account, and this
// card stays hidden then, so the other ladder admins never see it. See player_log.py.
const { authHeader } = useAuth()
const isBrowser = typeof window !== 'undefined'
const base = isBrowser ? '' : (useRuntimeConfig().public.apiBase || '')

const allowed = ref(false)
const tab = ref('joins')
const q = ref('')
const server = ref('')
const aliasOnly = ref(false)
const rows = ref([])
const total = ref(0)
const servers = ref([])
const loading = ref(false)
const err = ref('')
const editIp = ref(null)      // IP whose normal nick is being edited
const editNick = ref('')
const editNote = ref('')
const PAGE = 100

const STATUS = {
  normal: { label: 'normal', cls: 'mute' },
  'alias?': { label: 'alias?', cls: 'warn' },
  alias: { label: 'alias ✓', cls: 'bad' },
  separate: { label: 'separate', cls: 'info' },
  proxy: { label: 'proxy', cls: 'mute' },
}

let seq = 0  // only the newest request may fill the table (typing fires several)
async function load(more = false) {
  const mine = ++seq
  loading.value = true; err.value = ''
  const p = new URLSearchParams({ limit: PAGE, offset: more ? rows.value.length : 0 })
  if (q.value.trim()) p.set('q', q.value.trim())
  if (aliasOnly.value && tab.value !== 'nicks') p.set('only', 'alias')
  if (server.value && tab.value === 'joins') p.set('server', server.value)
  try {
    const r = await $fetch(`${base}/api/admin/player-log/${tab.value}?${p}`, { headers: authHeader() })
    if (mine !== seq) return
    allowed.value = true
    const list = r.joins || r.ips || r.nicks || []
    rows.value = more ? rows.value.concat(list) : list
    total.value = r.total || 0
    if (r.servers) servers.value = r.servers
  } catch (e) {
    if (mine !== seq) return
    if (e?.status === 403 || e?.statusCode === 403) { allowed.value = false; return }
    allowed.value = true  // show the card with the error rather than hide it
    err.value = e?.data?.detail || 'could not load the join log'
  } finally { if (mine === seq) loading.value = false }
}

let timer = null
watch(q, () => { clearTimeout(timer); timer = setTimeout(() => load(), 300) })
watch([tab, server, aliasOnly], () => load())
onMounted(() => load())

function show(t, value) { q.value = value; tab.value = t; clearTimeout(timer); load() }

function fmt(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString([], { month: 'short', day: 'numeric', year: '2-digit', hour: 'numeric', minute: '2-digit' })
}
function day(ts) { return ts ? new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric', year: '2-digit' }) : '' }

async function post(path, body) {
  try {
    await $fetch(`${base}/api/admin/player-log/${path}`, { method: 'POST', headers: authHeader(), body })
    await load()
  } catch (e) { err.value = e?.data?.detail || 'save failed' }
}
const verdict = (ip, nick, v) => post('verdict', { ip, nick, verdict: v })
const makeNormal = (ip, nick) => post('ip-owner', { ip, nick })
function startEdit(r) { editIp.value = r.ip; editNick.value = r.manual ? r.owner : ''; editNote.value = r.note || '' }
async function saveEdit() { await post('ip-owner', { ip: editIp.value, nick: editNick.value, note: editNote.value }); editIp.value = null }
</script>

<template>
  <section v-if="allowed" class="card wide">
    <h2>Server join log <span class="count">{{ total }}</span>
      <span class="muted small">— only you can see this</span>
    </h2>
    <p class="muted small" style="margin:-4px 0 12px;">
      Every join on our servers, from each box's player log (updated every 5 minutes).
      Each IP has a <b>normal nick</b>: the one you set, or else the nick seen there on the most days.
      Any other nick on that IP is flagged as an alias of it. Proxy joins (qwfwd) carry the proxy's IP, so they're never judged.
    </p>

    <div class="tabs">
      <button v-for="t in [['joins', 'Joins'], ['ips', 'By IP'], ['nicks', 'By nick']]" :key="t[0]"
              class="tab" :class="{ on: tab === t[0] }" @click="tab = t[0]">{{ t[1] }}</button>
    </div>
    <div class="form" style="margin:10px 0;">
      <input v-model="q" placeholder="nick or IP (start of an IP works)">
      <select v-if="tab === 'joins'" v-model="server" style="flex:0 0 auto; min-width:150px;">
        <option value="">All servers</option>
        <option v-for="s in servers" :key="s.server" :value="s.server">{{ s.label }}</option>
      </select>
      <label v-if="tab !== 'nicks'" class="chk"><input v-model="aliasOnly" type="checkbox"> aliases only</label>
    </div>
    <p v-if="err" class="err-note">{{ err }}</p>

    <div class="tscroll">
      <!-- Joins: one row per session -->
      <table v-if="tab === 'joins'">
        <thead><tr><th>Last seen</th><th>Server</th><th>Nick</th><th>IP</th><th>Normal nick</th><th>Status</th><th>Client</th><th class="r">Maps</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.server + r.port + r.userid + r.ip + r.name_norm + r.first_at">
            <td class="mono nowrap" :title="'first ' + fmt(r.first_at)">{{ fmt(r.last_at) }}</td>
            <td class="nowrap">{{ r.server_label }} <span class="muted">{{ r.port }}</span></td>
            <td><a class="lnk" @click="show('nicks', r.name)">{{ r.name }}</a>
              <span v-if="r.spectator" class="tag mute">spec</span></td>
            <td class="mono"><a class="lnk" @click="show('ips', r.ip)">{{ r.ip }}</a></td>
            <td>{{ r.status === 'proxy' ? '' : r.owner }}<span v-if="r.manual" class="muted" title="set by you"> ✎</span></td>
            <td><span class="tag" :class="STATUS[r.status].cls">{{ STATUS[r.status].label }}</span></td>
            <td class="muted small nowrap">{{ r.client }}</td>
            <td class="r mono">{{ r.connects }}</td>
          </tr>
        </tbody>
      </table>

      <!-- By IP: normal nick + every nick seen there -->
      <table v-else-if="tab === 'ips'">
        <thead><tr><th>IP</th><th>Normal nick</th><th>Nicks seen (days)</th><th>First</th><th>Last</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.ip">
            <td class="mono nowrap">{{ r.ip }}<div v-if="r.proxy" class="tag mute">proxy</div></td>
            <td class="owner">
              <template v-if="editIp === r.ip">
                <input v-model="editNick" list="pl-nicks" placeholder="blank = automatic" class="inp">
                <datalist id="pl-nicks"><option v-for="n in r.nicks" :key="n.name_norm" :value="n.name" /></datalist>
                <input v-model="editNote" placeholder="note (optional)" class="inp">
                <div><button class="btn sm" @click="saveEdit">Save</button> <button class="btn sm ghost" @click="editIp = null">Cancel</button></div>
              </template>
              <template v-else>
                <strong>{{ r.proxy ? '—' : r.owner }}</strong>
                <span class="muted small"> {{ r.manual ? '(set by you)' : '(auto)' }}</span>
                <div v-if="r.note" class="muted small">{{ r.note }}</div>
                <button v-if="!r.proxy" class="btn sm ghost" style="margin-top:4px;" @click="startEdit(r)">Edit</button>
              </template>
            </td>
            <td>
              <div v-for="n in r.nicks" :key="n.name_norm" class="nick">
                <a class="lnk" @click="show('nicks', n.name)">{{ n.name }}</a>
                <span class="muted small">{{ n.days }}d</span>
                <span v-if="n.status !== 'normal'" class="tag" :class="STATUS[n.status].cls">{{ STATUS[n.status].label }}</span>
                <span v-if="n.status !== 'normal' && n.status !== 'proxy'" class="acts">
                  <button v-if="n.status !== 'alias'" class="mini" title="Confirm: this is the normal nick aliasing" @click="verdict(r.ip, n.name, 'alias')">✓ alias</button>
                  <button v-if="n.status !== 'separate'" class="mini" title="A different person on the same connection" @click="verdict(r.ip, n.name, 'separate')">separate</button>
                  <button v-if="n.status === 'alias' || n.status === 'separate'" class="mini" title="Clear your choice" @click="verdict(r.ip, n.name, null)">undo</button>
                  <button class="mini" title="Make this the IP's normal nick" @click="makeNormal(r.ip, n.name)">make normal</button>
                </span>
              </div>
            </td>
            <td class="mono nowrap small">{{ day(r.first_at) }}</td>
            <td class="mono nowrap small">{{ day(r.last_at) }}</td>
          </tr>
        </tbody>
      </table>

      <!-- By nick: the IPs it used and whose IP each is -->
      <table v-else>
        <thead><tr><th>Nick</th><th>Alias of</th><th>IPs (normal nick there)</th><th class="r">Days</th><th>Last</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.name_norm">
            <td><strong>{{ r.name }}</strong></td>
            <td><span v-for="a in r.alias_of" :key="a" class="tag warn" style="margin-right:4px;">{{ a }}</span></td>
            <td>
              <div v-for="i in r.ips.slice(0, 8)" :key="i.ip" class="nick">
                <a class="lnk mono" @click="show('ips', i.ip)">{{ i.ip }}</a>
                <span class="muted small">{{ i.status === 'proxy' ? 'proxy' : i.owner }} · {{ i.days }}d</span>
                <span v-if="i.status !== 'normal' && i.status !== 'proxy'" class="tag" :class="STATUS[i.status].cls">{{ STATUS[i.status].label }}</span>
              </div>
              <div v-if="r.ips.length > 8" class="muted small">+{{ r.ips.length - 8 }} more</div>
            </td>
            <td class="r mono">{{ r.days }}</td>
            <td class="mono nowrap small">{{ day(r.last_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="loading" class="muted small pad">Loading…</div>
    <div v-else-if="!rows.length" class="muted small pad">Nothing found.</div>
    <div v-else-if="rows.length < total" style="text-align:center; margin-top:10px;">
      <button class="btn sm ghost" @click="load(true)">Show more ({{ rows.length }} of {{ total }})</button>
    </div>
  </section>
</template>

<style scoped>
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; margin-bottom: 16px; }
/* wider than the 760px admin column: the log is a table */
.wide { width: min(1180px, calc(100vw - 32px)); position: relative; left: 50%; transform: translateX(-50%); }
.card h2 { font-size: 15px; font-weight: 800; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card h2 .count { background: var(--panel-2); color: var(--fg-2); border-radius: 999px; padding: 1px 8px; font-size: 12px; }
.muted { color: var(--fg-2); }
.small { font-size: 12px; }
.pad { padding: 20px 0; text-align: center; }
.err-note { background: rgba(239,68,68,0.12); color: #fca5a5; padding: 8px 14px; border-radius: 8px; font-size: 13px; }
.tabs { display: inline-flex; gap: 4px; padding: 4px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 999px; }
.tab { background: none; border: 0; color: var(--fg-2); font-family: inherit; font-weight: 700; font-size: 13px; padding: 6px 14px; border-radius: 999px; cursor: pointer; }
.tab.on { background: var(--accent); color: #140a03; }
.form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.form input:not([type=checkbox]), .form select, .inp { background: var(--panel-2); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; border-radius: 7px; font-family: inherit; font-size: 13px; flex: 1; min-width: 140px; }
.inp { display: block; width: 100%; margin-bottom: 4px; padding: 5px 8px; }
.chk { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--fg-2); white-space: nowrap; }
.tscroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-size: 11px; font-weight: 700; color: var(--fg-3); text-transform: uppercase; letter-spacing: .04em; padding: 6px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; }
td { padding: 7px 8px; border-top: 1px solid var(--border); vertical-align: top; }
.r { text-align: right; }
.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.nowrap { white-space: nowrap; }
.owner { min-width: 170px; }
.lnk { color: var(--fg); cursor: pointer; text-decoration: underline dotted var(--fg-3); text-underline-offset: 3px; }
.lnk:hover { color: var(--accent); }
.nick { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 2px 0; }
.acts { display: inline-flex; gap: 4px; }
.mini { background: transparent; border: 1px solid var(--border); color: var(--fg-2); border-radius: 5px; padding: 1px 6px; font-size: 11px; font-family: inherit; cursor: pointer; }
.mini:hover { border-color: var(--accent); color: var(--fg); }
.tag { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
.tag.mute { background: var(--panel-2); color: var(--fg-3); }
.tag.warn { background: rgba(245,158,11,0.15); color: var(--draw); }
.tag.bad { background: rgba(239,68,68,0.15); color: var(--loss); }
.tag.info { background: rgba(74,159,255,0.15); color: var(--accent-2); }
.btn { background: var(--accent); color: var(--bg); border: 0; padding: 8px 14px; border-radius: 7px; font-weight: 700; font-size: 13px; cursor: pointer; font-family: inherit; }
.btn.sm { padding: 5px 11px; font-size: 12px; }
.btn.ghost { background: transparent; color: var(--fg-2); border: 1px solid var(--border); }
</style>
