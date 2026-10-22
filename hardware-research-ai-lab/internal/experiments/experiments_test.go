package experiments

import (
	"errors"
	"path/filepath"
	"strings"
	"testing"

	"hrail/internal/storage"
)

var ab = []Level{LevelA, LevelB}

func base() Experiment {
	return Experiment{ID: "EXP-1", Description: "d", HypothesisSource: "s", ApplicableHardware: []string{"gpu"},
		OperationalRisk: "baixo", Reversibility: "total", Confidence: "baixa", Level: LevelA, Kind: "analise", Origin: "estimated"}
}

func TestEstadoDeEvidenciaDistingueAusenciaDeIncompatibilidade(t *testing.T) {
	e := base()
	if e.State() != SemEvidencia {
		t.Fatal("sem evidências deve ser sem_evidencia")
	}
	cl, err := Classify(e, ab)
	if err != nil {
		t.Fatal(err)
	}
	if cl.EvidenceState == EvidIncompativel || !strings.Contains(strings.Join(cl.Notes, " "), "NÃO indica incompatibilidade") {
		t.Errorf("parecer: %+v", cl)
	}
	e.Contrary = []Evidence{{Summary: "x", URL: "https://example.org"}}
	if e.State() != EvidIncompativel {
		t.Error("contrária → incompatibilidade")
	}
	e.Favorable = []Evidence{{Summary: "y"}}
	if e.State() != EvidConflitante {
		t.Error("ambas → conflitante")
	}
	e.Contrary = nil
	if e.State() != EvidFavoravel {
		t.Error("favorável")
	}
}

func TestSomenteABNaFase0(t *testing.T) {
	for _, l := range []Level{LevelC, LevelD, LevelE} {
		e := base()
		e.Level = l
		_, err := Classify(e, ab)
		if !errors.Is(err, ErrNivelDesativado) {
			t.Errorf("nível %s deveria estar desativado: %v", l, err)
		}
		// mesmo se alguém tentar habilitar na configuração
		if _, err := Classify(e, []Level{l}); !errors.Is(err, ErrNivelDesativado) {
			t.Errorf("nível %s não pode ser habilitado na Fase 0: %v", l, err)
		}
	}
	e := base()
	e.Level = LevelB
	if cl, err := Classify(e, ab); err != nil || !cl.Phase0Allowed {
		t.Errorf("B deve ser permitido: %v", err)
	}
}

func TestIncoerencias(t *testing.T) {
	cases := map[string]func(*Experiment){
		"risco alto em A":     func(e *Experiment) { e.OperationalRisk = "alto" },
		"irreversível em B":   func(e *Experiment) { e.Level = LevelB; e.Reversibility = "irreversivel" },
		"confiança alta s/ev": func(e *Experiment) { e.Confidence = "alta" },
		"origem inválida":     func(e *Experiment) { e.Origin = "chute" },
		"nível inválido":      func(e *Experiment) { e.Level = "Z" },
		"id vazio":            func(e *Experiment) { e.ID = "" },
		"risco inválido":      func(e *Experiment) { e.OperationalRisk = "x" },
	}
	for name, f := range cases {
		e := base()
		f(&e)
		if _, err := Classify(e, ab); err == nil {
			t.Errorf("%s: deveria falhar", name)
		}
	}
}

func TestRegistroEConsulta(t *testing.T) {
	db, err := storage.Open(filepath.Join(t.TempDir(), "e.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	e := base()
	e.Favorable = []Evidence{{Summary: "commit X", URL: "https://example.org/x"}}
	e.Contrary = []Evidence{{Summary: "issue Y"}}
	if err := Save(db, e, ab); err != nil {
		t.Fatal(err)
	}
	if err := Save(db, e, ab); err == nil {
		t.Fatal("id duplicado deve falhar")
	}
	bad := base()
	bad.ID, bad.Level = "EXP-C", LevelC
	if err := Save(db, bad, ab); !errors.Is(err, ErrNivelDesativado) {
		t.Fatalf("nível C não deve ser persistido: %v", err)
	}
	es, err := List(db)
	if err != nil || len(es) != 1 || es[0].State() != EvidConflitante {
		t.Fatalf("list: %+v %v", es, err)
	}
	got, err := Get(db, "EXP-1")
	if err != nil || got.Description != "d" {
		t.Fatalf("get: %+v %v", got, err)
	}
	var n int
	db.SQL().QueryRow(`SELECT COUNT(*) FROM evidences WHERE experiment_id='EXP-1'`).Scan(&n)
	if n != 2 {
		t.Errorf("evidências=%d", n)
	}
}
