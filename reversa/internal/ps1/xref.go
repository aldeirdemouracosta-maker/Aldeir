package ps1

// XRef é uma referência do código a um endereço de dados.
type XRef struct {
	PC, Func uint32 // instrução e o início de função conhecido mais próximo antes dela (aproximação)
	Op       string // lw, sb, ... ou "monta endereço" (addiu/ori que forma o endereço)
	Store    bool
	Known    bool // escrita com valor constante conhecido
	Value    uint32
	Width    int
	Indexed  bool   // acesso a tabela: base conhecida e índice variável
	Addr     uint32 // endereço efetivo (a base da tabela, se Indexed)
}

var (
	memOps   = map[uint32]string{0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x26: "lwr", 0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2E: "swr"}
	memWidth = map[uint32]int{0x20: 1, 0x21: 2, 0x22: 4, 0x23: 4, 0x24: 1, 0x25: 2, 0x26: 4, 0x28: 1, 0x29: 2, 0x2A: 4, 0x2B: 4, 0x2E: 4}
)

// DataXrefs lista, em ordem de endereço, as instruções que leem, escrevem ou montam um endereço em
// [target, target+n). Usa propagação de constantes por função (sem seguir desvios), então acessos por
// ponteiros calculados de outro jeito não aparecem. Acessos a tabelas com índice variável aparecem como Indexed,
// com a base da tabela.
func (e *Exe) DataXrefs(target uint32, n int) []XRef {
	if n < 1 {
		n = 1
	}
	lo := target & 0x1FFFFFFF
	hi := lo + uint32(n)
	in := func(a uint32) bool { a &= 0x1FFFFFFF; return a >= lo && a < hi }
	starts := e.callTargets()
	var out []XRef
	c := e.newConsts()
	resetAt := -1
	for off, i := 0, 0; off+4 <= len(e.Text); off, i = off+4, i+1 {
		pc := e.Load + uint32(off)
		if _, isStart := starts[pc]; isStart || i == resetAt {
			c = e.newConsts()
		}
		w := le.Uint32(e.Text[off:])
		op, rs, rt := w>>26, w>>21&31, w>>16&31
		if _, isMem := memOps[op]; isMem {
			if eff, idx, ok := c.effective(rs, int32(int16(w))); ok && in(eff) {
				x := XRef{PC: pc, Op: memOps[op], Store: op >= 0x28, Indexed: idx, Addr: eff, Width: memWidth[op]}
				if op == 0x28 || op == 0x29 || op == 0x2B {
					if c.ok[rt] {
						x.Known, x.Value = true, c.val[rt]
						if x.Width < 4 {
							x.Value &= 1<<(8*x.Width) - 1
						}
					}
				}
				x.Func, _ = e.NearestStart(pc)
				out = append(out, x)
			}
		}
		c.step(w)
		if _, isMem := memOps[op]; !isMem && c.lastOK && in(c.lastVal) {
			f, _ := e.NearestStart(pc)
			out = append(out, XRef{PC: pc, Func: f, Op: "monta endereço", Addr: c.lastVal})
		}
		if op == 2 || (op == 0 && w&0x3F == 0x08) {
			resetAt = i + 2
		}
	}
	return out
}
