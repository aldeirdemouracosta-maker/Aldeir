// Package experiments implementa o mapa de risco e o registro de experimentos.
package experiments

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"hrail/internal/storage"
)

// Level é o nível de risco (A–E).
type Level string

const (
	LevelA Level = "A" // análise offline, sem executar código de hardware
	LevelB Level = "B" // diagnóstico/benchmark leve em espaço de usuário
	LevelC Level = "C" // experimento isolado com código de GPU
	LevelD Level = "D" // alteração de driver em ambiente controlado
	LevelE Level = "E" // kernel, firmware ou alteração persistente
)

var levelDesc = map[Level]string{
	LevelA: "análise offline, sem executar código de hardware",
	LevelB: "diagnóstico e benchmark leve em espaço de usuário",
	LevelC: "experimento isolado com código de GPU",
	LevelD: "alteração de driver em ambiente controlado",
	LevelE: "kernel, firmware ou alteração persistente",
}

func (l Level) Description() string { return levelDesc[l] }
func (l Level) Valid() bool         { _, ok := levelDesc[l]; return ok }

// Phase0Allowed: somente A e B podem ser considerados na Fase 0.
func (l Level) Phase0Allowed() bool { return l == LevelA || l == LevelB }

// ErrNivelDesativado indica nível não habilitado.
var ErrNivelDesativado = errors.New("nível desativado na Fase 0")

// Valores categóricos.
type (
	Risk          string // baixo | medio | alto
	Reversibility string // total | parcial | irreversivel
	Confidence    string // nenhuma | baixa | media | alta
)

// EvidenceState distingue AUSÊNCIA de evidência de EVIDÊNCIA de incompatibilidade.
type EvidenceState string

const (
	SemEvidencia     EvidenceState = "sem_evidencia" // nada foi encontrado: NÃO significa incompatível
	EvidFavoravel    EvidenceState = "evidencia_favoravel"
	EvidIncompativel EvidenceState = "evidencia_de_incompatibilidade" // há evidência contrária registrada
	EvidConflitante  EvidenceState = "evidencia_conflitante"
)

// Evidence é um item de evidência com URL/fonte.
type Evidence struct {
	Summary string `json:"summary"`
	URL     string `json:"url,omitempty"`
}

// Experiment é um experimento/hipótese classificada.
type Experiment struct {
	ID                         string        `json:"id"`
	Description                string        `json:"description"`
	HypothesisSource           string        `json:"hypothesis_source"`
	ApplicableHardware         []string      `json:"applicable_hardware"`
	Favorable                  []Evidence    `json:"favorable_evidence"`
	Contrary                   []Evidence    `json:"contrary_evidence"`
	Prerequisites              []string      `json:"prerequisites"`
	PotentialImpact            string        `json:"potential_impact"`
	OperationalRisk            Risk          `json:"operational_risk"`
	Reversibility              Reversibility `json:"reversibility"`
	Confidence                 Confidence    `json:"confidence"`
	RequiresPhysicalValidation bool          `json:"requires_physical_validation"`
	Level                      Level         `json:"level"`
	Kind                       string        `json:"kind"`
	Origin                     string        `json:"origin"` // measured | simulated | estimated | fixture
	InfrastructureTest         bool          `json:"infrastructure_test"`
	CreatedAt                  string        `json:"created_at,omitempty"`
}

// State calcula o estado de evidência.
func (e Experiment) State() EvidenceState {
	switch {
	case len(e.Favorable) > 0 && len(e.Contrary) > 0:
		return EvidConflitante
	case len(e.Contrary) > 0:
		return EvidIncompativel
	case len(e.Favorable) > 0:
		return EvidFavoravel
	}
	return SemEvidencia
}

var origins = map[string]bool{"measured": true, "simulated": true, "estimated": true, "fixture": true}

// Classification é o parecer sobre um experimento.
type Classification struct {
	Level         Level         `json:"level"`
	LevelDesc     string        `json:"level_description"`
	Phase0Allowed bool          `json:"phase0_allowed"`
	EvidenceState EvidenceState `json:"evidence_state"`
	Notes         []string      `json:"notes"`
}

// Classify valida a coerência e devolve o parecer. Erro ⇒ experimento inválido ou bloqueado.
func Classify(e Experiment, enabled []Level) (Classification, error) {
	c := Classification{Level: e.Level, LevelDesc: e.Level.Description(), EvidenceState: e.State()}
	var errs []string
	if strings.TrimSpace(e.ID) == "" {
		errs = append(errs, "id vazio")
	}
	if strings.TrimSpace(e.Description) == "" {
		errs = append(errs, "descrição vazia")
	}
	if !e.Level.Valid() {
		errs = append(errs, fmt.Sprintf("nível %q inválido", e.Level))
	}
	if !origins[e.Origin] {
		errs = append(errs, fmt.Sprintf("origem %q inválida (measured|simulated|estimated|fixture)", e.Origin))
	}
	switch e.OperationalRisk {
	case "baixo", "medio", "alto":
	default:
		errs = append(errs, "operational_risk deve ser baixo|medio|alto")
	}
	switch e.Reversibility {
	case "total", "parcial", "irreversivel":
	default:
		errs = append(errs, "reversibility deve ser total|parcial|irreversivel")
	}
	switch e.Confidence {
	case "nenhuma", "baixa", "media", "alta":
	default:
		errs = append(errs, "confidence deve ser nenhuma|baixa|media|alta")
	}
	if e.Confidence == "alta" && len(e.Favorable) == 0 {
		errs = append(errs, "confiança alta exige evidência favorável registrada")
	}
	if e.State() == SemEvidencia {
		c.Notes = append(c.Notes, "sem evidência registrada: isto NÃO indica incompatibilidade, apenas desconhecimento")
	}
	if e.State() == EvidIncompativel {
		c.Notes = append(c.Notes, "há evidência contrária registrada")
	}
	if (e.Level == LevelA || e.Level == LevelB) && (e.OperationalRisk == "alto" || e.Reversibility == "irreversivel") {
		errs = append(errs, "risco alto/irreversível é incoerente com nível A/B")
	}
	if e.Level == LevelA && e.Origin == "measured" && !e.InfrastructureTest {
		c.Notes = append(c.Notes, "nível A não executa código de hardware: origem 'measured' merece revisão")
	}
	if len(errs) > 0 {
		return c, errors.New(strings.Join(errs, "; "))
	}
	allowed := false
	for _, l := range enabled {
		allowed = allowed || l == e.Level
	}
	c.Phase0Allowed = allowed && e.Level.Phase0Allowed()
	if !c.Phase0Allowed {
		return c, fmt.Errorf("%w: nível %s (%s)", ErrNivelDesativado, e.Level, e.Level.Description())
	}
	return c, nil
}

// EnabledLevels converte strings de configuração.
func EnabledLevels(ss []string) []Level {
	var out []Level
	for _, s := range ss {
		out = append(out, Level(s))
	}
	return out
}

// Save valida e grava (insere) um experimento com suas evidências.
func Save(db *storage.DB, e Experiment, enabled []Level) error {
	if _, err := Classify(e, enabled); err != nil {
		return err
	}
	if e.CreatedAt == "" {
		e.CreatedAt = time.Now().UTC().Format(time.RFC3339)
	}
	b, _ := json.Marshal(e)
	tx, err := db.SQL().Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`INSERT INTO experiments(id,description,level,kind,origin,infrastructure_test,evidence_state,created_at,payload_json)
		VALUES(?,?,?,?,?,?,?,?,?)`, e.ID, e.Description, string(e.Level), e.Kind, e.Origin, b2i(e.InfrastructureTest),
		string(e.State()), e.CreatedAt, string(b)); err != nil {
		return err
	}
	ins := func(stance string, evs []Evidence) error {
		for _, ev := range evs {
			if _, err := tx.Exec(`INSERT INTO evidences(experiment_id,stance,url,summary,recorded_at) VALUES(?,?,NULLIF(?,''),?,?)`,
				e.ID, stance, ev.URL, ev.Summary, e.CreatedAt); err != nil {
				return err
			}
		}
		return nil
	}
	if err := ins("favoravel", e.Favorable); err != nil {
		return err
	}
	if err := ins("contraria", e.Contrary); err != nil {
		return err
	}
	return tx.Commit()
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

// List devolve os experimentos registrados, mais recentes primeiro.
func List(db *storage.DB) ([]Experiment, error) {
	rows, err := db.SQL().Query(`SELECT payload_json FROM experiments ORDER BY created_at DESC, id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Experiment
	for rows.Next() {
		var s string
		var e Experiment
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(s), &e); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}

// Get busca um experimento por id.
func Get(db *storage.DB, id string) (Experiment, error) {
	var s string
	var e Experiment
	if err := db.SQL().QueryRow(`SELECT payload_json FROM experiments WHERE id=?`, id).Scan(&s); err != nil {
		return e, err
	}
	return e, json.Unmarshal([]byte(s), &e)
}
