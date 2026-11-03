// Package match keeps the running state of one match from the parser's events: players and
// their stacks, item timers, the kill feed and the fight stats the live panels show.
package match

import (
	"math"
	"sort"
	"strings"

	"github.com/mvd-analyzer/mvd-reader/events"
	"github.com/mvd-analyzer/mvd-reader/mvd"
)

// fights: a damage chain between two players with gaps of at most 4 s (as in
// tools/mvd_features/agi_v0.py). The edge is the effective-HP difference at first contact;
// within 70 is an even fight (the duel fight table's 30-70% band).
const (
	fightGapMs = 4000
	evenEdge   = 70
	killWindow = 1500 // a death within 1.5 s of the last hit is that attacker's kill
)

type Status string

const (
	Warmup Status = "warmup"
	Live   Status = "live"
	Ended  Status = "ended"
)

type Player struct {
	Slot      int    `json:"slot"`
	Name      string `json:"name"`
	Team      string `json:"team"`
	Colors    [2]int `json:"colors"`
	Frags     int    `json:"frags"`
	Health    int    `json:"health"`
	Armor     int    `json:"armor"`
	ArmorType string `json:"armorType"` // "ra", "ya", "ga" or ""
	Eff       int    `json:"eff"`       // effective hp: what it takes to kill them
	Alive     bool   `json:"alive"`
	RL        bool   `json:"rl"`
	LG        bool   `json:"lg"`
	Rockets   int    `json:"rockets"`
	Cells     int    `json:"cells"`
	Quad      bool   `json:"quad"`
	Pent      bool   `json:"pent"`
	Ring      bool   `json:"ring"`

	Kills     int            `json:"kills"`
	Deaths    int            `json:"deaths"`
	Suicides  int            `json:"suicides"`
	DmgGiven  int            `json:"dmgGiven"`
	DmgTaken  int            `json:"dmgTaken"`
	Takes     map[string]int `json:"takes"` // ra, ya, ga, mh, quad, pent, ring, rl, lg
	TopSpeed  int            `json:"topSpeed"`
	Fights    FightRecord    `json:"fights"`
	spectator bool
	items     int
	lastPos   [3]float32
	lastPosMs int32
	hasPos    bool
}

// won/lost by the edge at first contact, from this player's side
type FightRecord struct {
	Ahead  WinLoss `json:"ahead"`
	Even   WinLoss `json:"even"`
	Behind WinLoss `json:"behind"`
}

type WinLoss struct {
	Won  int `json:"won"`
	Lost int `json:"lost"`
}

type Item struct {
	Ent       int        `json:"ent"`
	Kind      string     `json:"kind"`
	Origin    [3]float32 `json:"origin"`
	Up        bool       `json:"up"`
	TakenBy   string     `json:"takenBy,omitempty"`
	TakenAtMs int32      `json:"takenAtMs,omitempty"`
	// match ms when it comes back; 0 while unknown (a mega counts down only once its
	// holder is back to 100)
	RespawnAtMs int32 `json:"respawnAtMs,omitempty"`
	seen        bool
	holder      int // mega: the slot whose rot starts the 20 s countdown, -1 when none
}

type Kill struct {
	AtMs   int32  `json:"atMs"`
	Killer string `json:"killer"`
	Victim string `json:"victim"`
	Weapon string `json:"weapon"`
	Edge   *int   `json:"edge,omitempty"` // the killer's edge at first contact, when it was a fight
}

type Snapshot struct {
	Map         string    `json:"map"`
	Mode        string    `json:"mode"`
	Hostname    string    `json:"hostname"`
	Status      Status    `json:"status"`
	ClockMs     int32     `json:"clockMs"` // match time; negative before the start
	TimelimitMs int32     `json:"timelimitMs"`
	Players     []*Player `json:"players"`
	Items       []*Item   `json:"items"`
	Feed        []Kill    `json:"feed"`
}

type hit struct {
	attacker  int
	deathType int
	atMs      int32
}

type fight struct {
	startMs, lastMs int32
	edge            int // a's eff minus b's eff at first contact
}

type State struct {
	nowMs     int32
	startMs   int32
	started   bool
	ended     bool
	info      map[string]string
	mapFile   string
	players   map[int]*Player
	items     map[int]*Item
	feed      []Kill
	lastHit   map[int]hit
	fights    map[[2]int]*fight // keyed by (lower slot, higher slot)
}

func New() *State {
	return &State{
		info:    map[string]string{},
		players: map[int]*Player{},
		items:   map[int]*Item{},
		lastHit: map[int]hit{},
		fights:  map[[2]int]*fight{},
	}
}

var trackedItems = map[string]bool{
	"ra": true, "ya": true, "ga": true, "mh": true, "quad": true, "pent": true, "ring": true,
	"rl": true, "lg": true, "gl": true,
}

func (s *State) player(slot int) *Player {
	p := s.players[slot]
	if p == nil {
		p = &Player{Slot: slot, Takes: map[string]int{}}
		s.players[slot] = p
	}
	return p
}

func (s *State) clock(ms int32) int32 {
	if !s.started {
		return ms - s.nowMs // before the start everything is "now"
	}
	return ms - s.startMs
}

// Apply folds one parser event into the state.
func (s *State) Apply(ev events.Event) {
	switch e := ev.(type) {
	case *events.StuffTextEvent:
		if rest, ok := strings.CutPrefix(e.Command, "fullserverinfo "); ok {
			parseInfo(strings.Trim(strings.TrimSpace(rest), `"`), s.info)
		}
	case *events.ServerInfoEvent:
		s.info[e.Key] = e.Value
		s.nowMs = max(s.nowMs, e.TimeMs)
	case *events.ServerDataEvent:
		if e.Data != nil && e.Data.MapFile != "" {
			s.mapFile = e.Data.MapFile
		}
	case *events.UserInfoEvent:
		if e.Player == nil {
			return
		}
		p := s.player(e.Player.Slot)
		if e.Vacated {
			delete(s.players, e.Player.Slot)
			return
		}
		p.Name, p.Team = e.Player.Name, e.Player.Team
		p.Colors = [2]int{e.Player.TopColor, e.Player.BottomColor}
		p.spectator = e.Player.Spectator
	case *events.MatchStartEvent:
		if !s.started {
			s.started, s.startMs = true, e.TimeMs
			// warmup frags and takes do not count
			for _, p := range s.players {
				*p = Player{Slot: p.Slot, Name: p.Name, Team: p.Team, Colors: p.Colors, Takes: map[string]int{},
					Health: p.Health, Armor: p.Armor, ArmorType: p.ArmorType, Alive: p.Alive, items: p.items,
					RL: p.RL, LG: p.LG, Rockets: p.Rockets, Cells: p.Cells, spectator: p.spectator}
			}
			s.feed = nil
			s.fights = map[[2]int]*fight{}
		}
	case *events.IntermissionEvent:
		if s.started {
			s.ended = true
		}
	case *events.FragUpdateEvent:
		s.player(e.PlayerNum).Frags = e.Frags
	case *events.StatUpdateEvent:
		s.stat(e)
	case *events.PlayerPositionEvent:
		s.position(e)
	case *events.ItemSpawnEvent:
		if trackedItems[e.Kind] {
			s.items[e.EntNum] = &Item{Ent: e.EntNum, Kind: e.Kind, Origin: e.Origin, Up: true, seen: true}
		}
	case *events.ItemStateEvent:
		if it := s.items[e.EntNum]; it != nil {
			it.Up = !e.Taken
			if it.Up {
				it.seen = true
				it.RespawnAtMs = 0
			}
		}
	case *events.ItemPickupHintEvent:
		it := s.items[e.ItemEnt]
		if it == nil {
			return
		}
		p := s.player(e.PlayerEnt - 1)
		it.Up = false
		it.TakenBy = p.Name
		it.TakenAtMs = s.clock(e.TimeMs)
		it.RespawnAtMs = 0
		it.holder = -1
		if e.RespawnSec > 0 {
			it.RespawnAtMs = it.TakenAtMs + int32(e.RespawnSec)*1000
		} else if it.Kind == "mh" {
			it.holder = p.Slot
		}
		if s.started && !s.ended {
			p.Takes[it.Kind]++
		}
	case *events.DamageEvent:
		s.damage(e)
	case *events.DeathEvent:
		s.death(e)
	}
	if t, ok := ev.(interface{ EventTimeMs() int32 }); ok {
		s.nowMs = max(s.nowMs, t.EventTimeMs())
	}
}

func (s *State) stat(e *events.StatUpdateEvent) {
	p := s.player(e.PlayerNum)
	switch e.StatIndex {
	case mvd.StatHealth:
		p.Health = e.Value
		p.Alive = e.Value > 0
		// a mega comes back 20 s after its holder rots (or bleeds) down to 100, or dies
		for _, it := range s.items {
			if it.Kind == "mh" && it.holder == e.PlayerNum && !it.Up && it.RespawnAtMs == 0 && e.Value <= 100 {
				it.RespawnAtMs = s.clock(e.TimeMs) + 20_000
				it.holder = -1
			}
		}
	case mvd.StatArmor:
		p.Armor = e.Value
	case mvd.StatRockets:
		p.Rockets = e.Value
	case mvd.StatCells:
		p.Cells = e.Value
	case mvd.StatItems:
		p.items = e.Value
		p.RL = e.Value&mvd.ITRocketLauncher != 0
		p.LG = e.Value&mvd.ITLightning != 0
		p.Quad = e.Value&mvd.ITQuad != 0
		p.Pent = e.Value&mvd.ITInvulnerability != 0
		p.Ring = e.Value&mvd.ITInvisibility != 0
		switch {
		case e.Value&mvd.ITArmor3 != 0:
			p.ArmorType = "ra"
		case e.Value&mvd.ITArmor2 != 0:
			p.ArmorType = "ya"
		case e.Value&mvd.ITArmor1 != 0:
			p.ArmorType = "ga"
		default:
			p.ArmorType = ""
		}
	}
	p.Eff = eff(p.Health, p.Armor, p.ArmorType)
}

// effective hp, as tools/mvd_features/extract.py eff()
func eff(health, armor int, armorType string) int {
	ratio := map[string]float64{"ra": 0.8, "ya": 0.6, "ga": 0.3}[armorType]
	if health <= 0 {
		return 0
	}
	if ratio > 0 && ratio*float64(health)/(1-ratio) <= float64(armor) {
		return int(math.Round(float64(health) / (1 - ratio)))
	}
	return health + armor
}

func (s *State) position(e *events.PlayerPositionEvent) {
	p := s.player(e.PlayerNum)
	if p.hasPos && p.Alive && s.started && !s.ended {
		dt := e.TimeMs - p.lastPosMs
		if dt >= 20 && dt <= 200 {
			dx, dy := e.Origin[0]-p.lastPos[0], e.Origin[1]-p.lastPos[1]
			speed := int(math.Hypot(float64(dx), float64(dy)) * 1000 / float64(dt))
			// teleports and respawns jump thousands of units at once
			if speed < 2500 && speed > p.TopSpeed {
				p.TopSpeed = speed
			}
		}
	}
	p.lastPos, p.lastPosMs, p.hasPos = e.Origin, e.TimeMs, true
}

func pair(a, b int) [2]int {
	if a < b {
		return [2]int{a, b}
	}
	return [2]int{b, a}
}

func (s *State) damage(e *events.DamageEvent) {
	if !s.started || s.ended || e.Victim < 0 {
		return
	}
	victim := s.player(e.Victim)
	victim.DmgTaken += e.Damage
	s.lastHit[e.Victim] = hit{attacker: e.Attacker, deathType: e.DeathType, atMs: e.TimeMs}
	if e.Attacker < 0 || e.Attacker == e.Victim {
		return
	}
	attacker := s.player(e.Attacker)
	if attacker.Team == "" || attacker.Team != victim.Team || len(s.teams()) < 2 {
		attacker.DmgGiven += e.Damage
	}
	key := pair(e.Attacker, e.Victim)
	f := s.fights[key]
	if f == nil || e.TimeMs-f.lastMs > fightGapMs {
		// first contact: both stacks before this hit landed
		a, b := s.player(key[0]), s.player(key[1])
		ea, eb := a.Eff, b.Eff
		if e.Victim == key[0] {
			ea += e.Damage
		} else {
			eb += e.Damage
		}
		f = &fight{startMs: e.TimeMs, edge: ea - eb}
		s.fights[key] = f
	}
	f.lastMs = e.TimeMs
}

func (s *State) death(e *events.DeathEvent) {
	if !s.started || s.ended {
		return
	}
	victim := s.player(e.PlayerNum)
	victim.Deaths++
	h, ok := s.lastHit[e.PlayerNum]
	delete(s.lastHit, e.PlayerNum)
	kill := Kill{AtMs: s.clock(e.TimeMs), Victim: victim.Name, Weapon: "world"}
	if ok && e.TimeMs-h.atMs <= killWindow {
		kill.Weapon = weaponName(h.deathType)
		if h.attacker >= 0 && h.attacker != e.PlayerNum {
			killer := s.player(h.attacker)
			killer.Kills++
			kill.Killer = killer.Name
			key := pair(h.attacker, e.PlayerNum)
			if f := s.fights[key]; f != nil && e.TimeMs-f.lastMs <= fightGapMs {
				edge := f.edge
				if h.attacker != key[0] {
					edge = -edge
				}
				kill.Edge = &edge
				bucket(&killer.Fights, edge).Won++
				bucket(&victim.Fights, -edge).Lost++
				delete(s.fights, key)
			}
		} else {
			victim.Suicides++
		}
	} else {
		victim.Suicides++
	}
	s.feed = append(s.feed, kill)
}

func bucket(r *FightRecord, edge int) *WinLoss {
	switch {
	case edge >= evenEdge:
		return &r.Ahead
	case edge <= -evenEdge:
		return &r.Behind
	default:
		return &r.Even
	}
}

func weaponName(dt int) string {
	switch dt {
	case mvd.DtAxe:
		return "axe"
	case mvd.DtSG:
		return "sg"
	case mvd.DtSSG:
		return "ssg"
	case mvd.DtNG:
		return "ng"
	case mvd.DtSNG:
		return "sng"
	case mvd.DtGL:
		return "gl"
	case mvd.DtRL:
		return "rl"
	case mvd.DtLGBeam, mvd.DtLGDischarge, mvd.DtLGDischargeSelf:
		return "lg"
	case mvd.DtStomp:
		return "stomp"
	case mvd.DtTele1, mvd.DtTele2, mvd.DtTele3, mvd.DtTele4:
		return "telefrag"
	default:
		return "world"
	}
}

func (s *State) teams() map[string]bool {
	t := map[string]bool{}
	for _, p := range s.players {
		if !p.spectator && p.Name != "" && p.Team != "" {
			t[p.Team] = true
		}
	}
	return t
}

func parseInfo(raw string, into map[string]string) {
	parts := strings.Split(strings.TrimPrefix(raw, `\`), `\`)
	for i := 0; i+1 < len(parts); i += 2 {
		into[parts[i]] = parts[i+1]
	}
}

// Snapshot is a copy of the state for the panels.
func (s *State) Snapshot() Snapshot {
	snap := Snapshot{
		Map:      s.info["map"],
		Mode:     s.info["mode"],
		Hostname: plain(s.info["hostname"]),
		Status:   Warmup,
		ClockMs:  s.clock(s.nowMs),
	}
	if snap.Map == "" {
		snap.Map = strings.TrimSuffix(strings.TrimPrefix(s.mapFile, "maps/"), ".bsp")
	}
	if tl, ok := atoi(s.info["timelimit"]); ok {
		snap.TimelimitMs = int32(tl) * 60_000
	}
	if s.started {
		snap.Status = Live
	}
	if s.ended {
		snap.Status = Ended
	}
	for _, p := range s.players {
		if p.spectator || p.Name == "" {
			continue
		}
		c := *p
		c.Takes = map[string]int{}
		for k, v := range p.Takes {
			c.Takes[k] = v
		}
		snap.Players = append(snap.Players, &c)
	}
	sort.Slice(snap.Players, func(i, j int) bool {
		if snap.Players[i].Frags != snap.Players[j].Frags {
			return snap.Players[i].Frags > snap.Players[j].Frags
		}
		return snap.Players[i].Slot < snap.Players[j].Slot
	})
	duel := snap.Mode == "1on1" || snap.Mode == "duel"
	for _, it := range s.items {
		// ktx keeps powerup entities in duels but never shows them (no quad in 1on1); an
		// item never seen up is not part of this match
		if !it.seen || duel && (it.Kind == "quad" || it.Kind == "pent" || it.Kind == "ring") {
			continue
		}
		c := *it
		snap.Items = append(snap.Items, &c)
	}
	sort.Slice(snap.Items, func(i, j int) bool {
		if snap.Items[i].Kind != snap.Items[j].Kind {
			return itemOrder(snap.Items[i].Kind) < itemOrder(snap.Items[j].Kind)
		}
		return snap.Items[i].Ent < snap.Items[j].Ent
	})
	snap.Feed = append([]Kill(nil), s.feed...)
	return snap
}

func itemOrder(kind string) int {
	return strings.Index("quad pent ring ra   ya   ga   mh   rl   lg   gl", kind)
}

func atoi(v string) (int, bool) {
	n := 0
	if v == "" {
		return 0, false
	}
	for _, c := range v {
		if c < '0' || c > '9' {
			return 0, false
		}
		n = n*10 + int(c-'0')
	}
	return n, true
}

// plain turns quake charset text into ascii: the high bit is the coloured half of the font
func plain(v string) string {
	b := make([]rune, 0, len(v))
	for _, c := range v {
		c &= 0x7f
		if c >= 32 && c < 127 {
			b = append(b, c)
		}
	}
	return strings.TrimSpace(string(b))
}
