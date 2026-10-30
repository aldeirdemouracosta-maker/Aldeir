package ps1

import "strings"

// BIOSCall é uma função da BIOS do PS1. A convenção é: $t2 = 0xA0, 0xB0 ou 0xC0 (tabela), $t1 = número da
// função, e salto por 'jr $t2'. Os nomes das funções não estão aqui de propósito: só o que o código prova.
type BIOSCall struct {
	Table byte   // 0xA0, 0xB0 ou 0xC0
	Func  uint32 // número da função na tabela
}

// BIOSStub reconhece uma função que é só um stub de chamada à BIOS (por exemplo: addiu $t2,$zero,0xa0;
// jr $t2; addiu $t1,$zero,0x33). Examina no máximo 8 instruções.
func (e *Exe) BIOSStub(addr uint32) (BIOSCall, bool) {
	c := newConsts()
	for i := 0; i < 8; i++ {
		w, ok := e.Word(addr + uint32(i)*4)
		if !ok {
			return BIOSCall{}, false
		}
		if w>>26 == 0 && w&0x3F == 0x08 && w>>21&31 == 10 { // jr $t2
			if d, ok := e.Word(addr + uint32(i+1)*4); ok {
				c.step(d) // delay slot: costuma carregar o número em $t1
			}
			t := c.val[10]
			if c.ok[10] && c.ok[9] && (t == 0xA0 || t == 0xB0 || t == 0xC0) {
				return BIOSCall{Table: byte(t), Func: c.val[9]}, true
			}
			return BIOSCall{}, false
		}
		if w>>26 == 0 && w&0x3F == 0x09 || (w>>26 >= 4 && w>>26 <= 7) || w>>26 == 2 || w>>26 == 3 {
			return BIOSCall{}, false // outro tipo de salto antes: não é um stub simples
		}
		c.step(w)
	}
	return BIOSCall{}, false
}

// StringRef é uma referência do código a uma string ASCII dentro do próprio executável.
type StringRef struct {
	PC   uint32 // instrução que montou o endereço
	Addr uint32
	Text string
}

// StringRefs acha endereços montados por lui+addiu/ori que apontam para uma string ASCII legível dentro do
// executável. É uma heurística: texto em codificação própria do jogo (fonte customizada) não aparece.
func (e *Exe) StringRefs(addr uint32, n int) []StringRef {
	var out []StringRef
	seen := map[uint32]bool{}
	c := newConsts()
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		c.step(w)
		if !c.lastOK || seen[c.lastVal] {
			continue
		}
		if s, ok := e.asciiAt(c.lastVal); ok {
			seen[c.lastVal] = true
			out = append(out, StringRef{PC: pc, Addr: c.lastVal, Text: s})
		}
	}
	return out
}

// asciiAt lê uma string terminada em NUL com pelo menos 4 caracteres, quase toda legível.
func (e *Exe) asciiAt(a uint32) (string, bool) {
	if a < e.Load || uint64(a-e.Load) >= uint64(len(e.Text)) {
		return "", false
	}
	var b strings.Builder
	letters := 0
	for off := a - e.Load; int(off) < len(e.Text) && b.Len() < 64; off++ {
		ch := e.Text[off]
		if ch == 0 {
			break
		}
		if (ch < 0x20 || ch > 0x7E) && ch != '\n' && ch != '\r' && ch != '\t' { // formatos de printf têm \n
			return "", false
		}
		if ch|0x20 >= 'a' && ch|0x20 <= 'z' {
			letters++
		}
		b.WriteByte(ch)
	}
	if b.Len() < 4 || letters < 3 || letters*3 < b.Len() { // formatos como "%s: %d\n" têm muitos símbolos
		return "", false
	}
	return b.String(), true
}

// Recursive diz se a função chama a si mesma por jal.
func (e *Exe) Recursive(addr uint32, n int) bool {
	for _, c := range e.Callees(addr, n) {
		if c == addr {
			return true
		}
	}
	return false
}

// SyscallStub reconhece uma função que é só um 'syscall' do kernel com $a0 constante (por exemplo
// addiu $a0,$zero,1; syscall 0; jr $ra). Devolve o valor de $a0, que escolhe a função do kernel.
func (e *Exe) SyscallStub(addr uint32) (uint32, bool) {
	c := newConsts()
	for i := 0; i < 6; i++ {
		w, ok := e.Word(addr + uint32(i)*4)
		if !ok {
			return 0, false
		}
		if w>>26 == 0 && w&0x3F == 0x0C { // syscall
			return c.val[4], c.ok[4]
		}
		if op := w >> 26; op == 2 || op == 3 || (op >= 4 && op <= 7) || (op == 0 && (w&0x3F == 0x08 || w&0x3F == 0x09)) {
			return 0, false // salto antes do syscall: não é um stub simples
		}
		c.step(w)
	}
	return 0, false
}

// FuncLen devolve quantas instruções a função em addr ocupa (heurística de fim de função, até n).
func (e *Exe) FuncLen(addr uint32, n int) int { return e.span(addr, n) }
