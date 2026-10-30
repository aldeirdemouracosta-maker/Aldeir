package ps1

import "regexp"

var identPat = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_]{2,31}$`)

// NameHints devolve as strings que a função referencia e que parecem identificadores (como "CD_cw"): em código de
// biblioteca, o nome da função costuma aparecer em mensagens de depuração. É só uma pista: a string também pode
// ser o nome de outra função usada na mensagem.
func (e *Exe) NameHints(addr uint32, n int) []StringRef {
	var out []StringRef
	for _, r := range e.StringRefs(addr, n) {
		if identPat.MatchString(r.Text) {
			out = append(out, r)
		}
	}
	return out
}

// PointerSwap reconhece o padrão de instalar um callback: função curta que lê um ponteiro global em $v0 e grava
// $a0 nessa mesma global, devolvendo o valor antigo. Devolve o endereço da global.
func (e *Exe) PointerSwap(addr uint32) (global uint32, ok bool) {
	n := e.span(addr, 16)
	if n >= 16 { // não terminou: não é uma função curta
		return 0, false
	}
	c := e.newConsts()
	var loaded uint32
	haveLoad := false
	for i := 0; i < n; i++ {
		w, _ := e.Word(addr + uint32(i)*4)
		op, rs, rt := w>>26, w>>21&31, w>>16&31
		if op == 0x23 || op == 0x2B { // lw, sw
			if eff, indexed, found := c.effective(rs, int32(int16(w))); found && !indexed && HWName(eff) == "" {
				switch {
				case op == 0x23 && rt == 2:
					loaded, haveLoad = eff, true
				case op == 0x2B && rt == 4 && haveLoad && eff == loaded:
					return eff, true
				}
			}
		}
		c.step(w)
	}
	return 0, false
}
