package tools

import (
	"encoding/json"

	"hrail/internal/storage"
)

// Save grava (upsert) o estado das ferramentas.
func Save(db *storage.DB, cs []Check) error {
	for _, c := range cs {
		b, _ := json.Marshal(c)
		_, err := db.SQL().Exec(`INSERT INTO tools(id,name,category,status,version,path,checked_at,payload_json)
			VALUES(?,?,?,?,NULLIF(?,''),NULLIF(?,''),NULLIF(?,''),?)
			ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,status=excluded.status,
			version=excluded.version,path=excluded.path,checked_at=excluded.checked_at,payload_json=excluded.payload_json`,
			c.Def.ID, c.Def.Name, c.Def.Category, string(c.Status), c.Version, c.Path, c.CheckedAt, string(b))
		if err != nil {
			return err
		}
	}
	return nil
}

// Load lê o último estado gravado.
func Load(db *storage.DB) ([]Check, error) {
	rows, err := db.SQL().Query(`SELECT payload_json FROM tools ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Check
	for rows.Next() {
		var s string
		var c Check
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(s), &c); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}
