package gitscan

import (
	"encoding/json"

	"hrail/internal/storage"
)

// Save grava (upsert) os achados de uma fonte.
func Save(db *storage.DB, sourceID string, cs []Commit) error {
	tx, err := db.SQL().Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, c := range cs {
		kw, _ := json.Marshal(c.Keywords)
		is, _ := json.Marshal(c.IssueRefs)
		rev := 0
		if c.IsRevert {
			rev = 1
		}
		if _, err := tx.Exec(`INSERT INTO commit_findings(source_id,hash,commit_date,subject,is_revert,reverted_hash,keywords_json,issue_refs_json,scanned_at)
			VALUES(?,?,?,?,?,NULLIF(?,''),?,?,?)
			ON CONFLICT(source_id,hash) DO UPDATE SET commit_date=excluded.commit_date,subject=excluded.subject,
			is_revert=excluded.is_revert,reverted_hash=excluded.reverted_hash,keywords_json=excluded.keywords_json,
			issue_refs_json=excluded.issue_refs_json,scanned_at=excluded.scanned_at`,
			sourceID, c.Hash, c.Date, c.Subject, rev, c.RevertedHash, string(kw), string(is), storage.Now()); err != nil {
			return err
		}
	}
	return tx.Commit()
}

// Query filtra os achados gravados.
type Query struct {
	SourceID    string
	OnlyReverts bool
	Keyword     string
}

// List devolve achados gravados (mais recentes primeiro).
func List(db *storage.DB, q Query) ([]Commit, []string, error) {
	rows, err := db.SQL().Query(`SELECT source_id,hash,commit_date,subject,is_revert,COALESCE(reverted_hash,''),keywords_json,issue_refs_json
		FROM commit_findings WHERE (?='' OR source_id=?) AND (?=0 OR is_revert=1) ORDER BY commit_date DESC, hash`,
		q.SourceID, q.SourceID, b2i(q.OnlyReverts))
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	var out []Commit
	var srcs []string
	for rows.Next() {
		var c Commit
		var src, kw, is string
		var rev int
		if err := rows.Scan(&src, &c.Hash, &c.Date, &c.Subject, &rev, &c.RevertedHash, &kw, &is); err != nil {
			return nil, nil, err
		}
		c.IsRevert = rev == 1
		json.Unmarshal([]byte(kw), &c.Keywords)
		json.Unmarshal([]byte(is), &c.IssueRefs)
		if q.Keyword != "" && !contains(c.Keywords, q.Keyword) {
			continue
		}
		out = append(out, c)
		srcs = append(srcs, src)
	}
	return out, srcs, rows.Err()
}

// Exists informa se o commit (hash completo ou prefixo ≥7) foi analisado para a fonte.
func Exists(db *storage.DB, sourceID, hash string) (string, bool, error) {
	var full string
	err := db.SQL().QueryRow(`SELECT hash FROM commit_findings WHERE source_id=? AND hash LIKE ? || '%' LIMIT 2`, sourceID, hash).Scan(&full)
	if err != nil {
		if err.Error() == "sql: no rows in result set" {
			return "", false, nil
		}
		return "", false, err
	}
	return full, true, nil
}

func contains(ss []string, s string) bool {
	for _, x := range ss {
		if x == s {
			return true
		}
	}
	return false
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}
