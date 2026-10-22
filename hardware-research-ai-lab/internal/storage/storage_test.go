package storage

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hrail/internal/security"
)

func open(t *testing.T) *DB {
	t.Helper()
	db, err := Open(filepath.Join(t.TempDir(), "sub", "t.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func TestCriacaoEMigracao(t *testing.T) {
	db := open(t)
	v, err := db.SchemaVersion()
	if err != nil || v != 3 {
		t.Fatalf("versão=%d err=%v", v, err)
	}
	for _, tb := range append(ExportTables, "schema_migrations") {
		if _, err := db.SQL().Exec("SELECT 1 FROM " + tb + " LIMIT 1"); err != nil {
			t.Errorf("tabela %s ausente: %v", tb, err)
		}
	}
}

func TestMigracaoIdempotenteEIncremental(t *testing.T) {
	path := filepath.Join(t.TempDir(), "m.db")
	db, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	// simula banco antigo na v2
	db.SQL().Exec(`DROP TABLE source_verifications`)
	db.SQL().Exec(`DROP TABLE commit_findings`)
	db.SQL().Exec(`DELETE FROM schema_migrations WHERE version=3`)
	db.Close()
	db, err = Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if v, _ := db.SchemaVersion(); v != 3 {
		t.Fatalf("versão=%d", v)
	}
	if err := db.Migrate(); err != nil {
		t.Fatalf("segunda migração deve ser no-op: %v", err)
	}
	var n int
	db.SQL().QueryRow(`SELECT COUNT(*) FROM schema_migrations`).Scan(&n)
	if n != 3 {
		t.Fatalf("linhas de migração=%d", n)
	}
	if v, err := Inspect(path); err != nil || v != 3 {
		t.Fatalf("Inspect=%d %v", v, err)
	}
}

func TestExportJSONeCSV(t *testing.T) {
	db := open(t)
	if _, err := db.SaveHardware("fixture", map[string]string{"k": "v"}); err != nil {
		t.Fatal(err)
	}
	db.LogCommand(security.CommandRecord{Time: time.Now(), Command: "echo", Args: []string{"a"}, ExitCode: 0, Duration: "1ms"})
	var b bytes.Buffer
	if err := db.ExportJSON(&b); err != nil {
		t.Fatal(err)
	}
	var out map[string][]map[string]any
	if err := json.Unmarshal(b.Bytes(), &out); err != nil {
		t.Fatalf("JSON inválido: %v", err)
	}
	if len(out["hardware_snapshots"]) != 1 || len(out["command_log"]) != 1 {
		t.Fatalf("export incompleto: %v", out)
	}
	b.Reset()
	if err := db.ExportCSV("hardware_snapshots", &b); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(b.String()), "\n")
	if len(lines) != 2 || !strings.HasPrefix(lines[0], "id,collected_at,origin") {
		t.Fatalf("CSV inesperado: %q", b.String())
	}
	if err := db.ExportCSV("sqlite_master; DROP TABLE x", &b); err == nil {
		t.Fatal("tabela fora da lista deve ser recusada")
	}
}

func TestOrigemInvalidaRejeitadaPeloBanco(t *testing.T) {
	db := open(t)
	if _, err := db.SaveHardware("inventada", 1); err == nil {
		t.Fatal("CHECK de origem deveria rejeitar")
	}
}
