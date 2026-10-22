// Package storage implementa o banco SQLite local (experiment-database).
package storage

import (
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"hrail/internal/security"
	"hrail/migrations"
)

// DB encapsula a conexão SQLite.
type DB struct{ sql *sql.DB }

// Open abre (criando se preciso) o banco em path e aplica as migrações.
func Open(path string) (*DB, error) {
	if path != ":memory:" {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return nil, err
		}
	}
	s, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, err
	}
	s.SetMaxOpenConns(1)
	for _, p := range []string{"PRAGMA foreign_keys=ON", "PRAGMA busy_timeout=5000"} {
		if _, err := s.Exec(p); err != nil {
			s.Close()
			return nil, err
		}
	}
	db := &DB{sql: s}
	if err := db.Migrate(); err != nil {
		s.Close()
		return nil, err
	}
	return db, nil
}

// Close fecha o banco.
func (d *DB) Close() error { return d.sql.Close() }

// SQL expõe a conexão para consultas específicas de módulos.
func (d *DB) SQL() *sql.DB { return d.sql }

// Migrate aplica as migrações pendentes, em ordem, cada uma em transação.
func (d *DB) Migrate() error {
	if _, err := d.sql.Exec(`CREATE TABLE IF NOT EXISTS schema_migrations (
		version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)`); err != nil {
		return err
	}
	entries, err := fs.ReadDir(migrations.FS, ".")
	if err != nil {
		return err
	}
	var names []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".sql") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, n := range names {
		v, err := strconv.Atoi(strings.SplitN(n, "_", 2)[0])
		if err != nil {
			return fmt.Errorf("migração %q sem prefixo numérico", n)
		}
		var exists int
		if err := d.sql.QueryRow(`SELECT COUNT(*) FROM schema_migrations WHERE version=?`, v).Scan(&exists); err != nil {
			return err
		}
		if exists > 0 {
			continue
		}
		body, err := fs.ReadFile(migrations.FS, n)
		if err != nil {
			return err
		}
		tx, err := d.sql.Begin()
		if err != nil {
			return err
		}
		if _, err := tx.Exec(string(body)); err != nil {
			tx.Rollback()
			return fmt.Errorf("migração %s falhou: %w", n, err)
		}
		if _, err := tx.Exec(`INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)`,
			v, n, now()); err != nil {
			tx.Rollback()
			return err
		}
		if err := tx.Commit(); err != nil {
			return err
		}
	}
	return nil
}

// SchemaVersion devolve a maior versão aplicada.
func (d *DB) SchemaVersion() (int, error) {
	var v sql.NullInt64
	if err := d.sql.QueryRow(`SELECT MAX(version) FROM schema_migrations`).Scan(&v); err != nil {
		return 0, err
	}
	return int(v.Int64), nil
}

func now() string { return time.Now().UTC().Format(time.RFC3339) }

// Now exposto para módulos que gravam timestamps consistentes.
func Now() string { return now() }

// LogCommand persiste um registro de comando externo.
func (d *DB) LogCommand(r security.CommandRecord) error {
	a, _ := json.Marshal(r.Args)
	_, err := d.sql.Exec(`INSERT INTO command_log(time,command,args_json,exit_code,duration,timed_out,error)
		VALUES(?,?,?,?,?,?,?)`, r.Time.Format(time.RFC3339), r.Command, string(a), r.ExitCode, r.Duration,
		b2i(r.TimedOut), r.Error)
	return err
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

// SaveHardware grava um snapshot de hardware e devolve o id.
func (d *DB) SaveHardware(origin string, payload any) (int64, error) {
	b, err := json.Marshal(payload)
	if err != nil {
		return 0, err
	}
	res, err := d.sql.Exec(`INSERT INTO hardware_snapshots(collected_at,origin,payload_json) VALUES(?,?,?)`,
		now(), origin, string(b))
	if err != nil {
		return 0, err
	}
	return res.LastInsertId()
}

// TableNames lista as tabelas exportáveis.
var ExportTables = []string{"hardware_snapshots", "sources", "tools", "experiments", "evidences", "results", "command_log", "source_verifications", "commit_findings", "third_party_reviews", "simulation_builds", "simulation_runs"}

// ExportJSON escreve todas as tabelas como {tabela: [linhas]}.
func (d *DB) ExportJSON(w io.Writer) error {
	out := map[string][]map[string]any{}
	for _, t := range ExportTables {
		rows, err := d.rows(t)
		if err != nil {
			return err
		}
		out[t] = rows
	}
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(out)
}

// ExportCSV escreve uma tabela em CSV.
func (d *DB) ExportCSV(table string, w io.Writer) error {
	ok := false
	for _, t := range ExportTables {
		ok = ok || t == table
	}
	if !ok {
		return fmt.Errorf("tabela %q não exportável", table)
	}
	rows, err := d.sql.Query("SELECT * FROM " + table)
	if err != nil {
		return err
	}
	defer rows.Close()
	cols, _ := rows.Columns()
	cw := csv.NewWriter(w)
	cw.Write(cols)
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return err
		}
		rec := make([]string, len(cols))
		for i, v := range vals {
			rec[i] = fmt.Sprint(norm(v))
		}
		cw.Write(rec)
	}
	cw.Flush()
	if err := cw.Error(); err != nil {
		return err
	}
	return rows.Err()
}

func norm(v any) any {
	switch x := v.(type) {
	case nil:
		return ""
	case []byte:
		return string(x)
	}
	return v
}

func (d *DB) rows(table string) ([]map[string]any, error) {
	rows, err := d.sql.Query("SELECT * FROM " + table)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cols, _ := rows.Columns()
	res := []map[string]any{}
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		m := map[string]any{}
		for i, c := range cols {
			m[c] = norm(vals[i])
		}
		res = append(res, m)
	}
	return res, rows.Err()
}

// Inspect abre o banco existente em modo somente leitura (sem migrar) e devolve a versão do esquema.
func Inspect(path string) (int, error) {
	if _, err := os.Stat(path); err != nil {
		return 0, err
	}
	s, err := sql.Open("sqlite", "file:"+path+"?mode=ro")
	if err != nil {
		return 0, err
	}
	defer s.Close()
	var v sql.NullInt64
	if err := s.QueryRow(`SELECT MAX(version) FROM schema_migrations`).Scan(&v); err != nil {
		return 0, err
	}
	return int(v.Int64), nil
}
