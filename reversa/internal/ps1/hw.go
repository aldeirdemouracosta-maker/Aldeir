package ps1

import "fmt"

// Nomes de registradores de E/S do PS1 (conforme a documentação psx-spx, de memória: confira ao ampliar).
// O PS1 espelha a E/S em 0x1F80xxxx, 0x9F80xxxx (KSEG0) e 0xBF80xxxx (KSEG1).

var dmaChannel = [7]string{"MDECin", "MDECout", "GPU", "CDROM", "SPU", "PIO", "OTC"}

var hwFixed = map[uint32]string{
	0x1F801040: "JOY_DATA", 0x1F801044: "JOY_STAT", 0x1F801048: "JOY_MODE", 0x1F80104A: "JOY_CTRL", 0x1F80104E: "JOY_BAUD",
	0x1F801070: "I_STAT", 0x1F801074: "I_MASK",
	0x1F8010F0: "DMA_DPCR", 0x1F8010F4: "DMA_DICR",
	0x1F801800: "CDROM_INDEX", 0x1F801801: "CDROM_REG1", 0x1F801802: "CDROM_REG2", 0x1F801803: "CDROM_REG3",
	0x1F801810: "GPU_GP0", 0x1F801814: "GPU_GP1",
	0x1F801820: "MDEC_CMD", 0x1F801824: "MDEC_CTRL",
	0x1F801D80: "SPU_MAIN_VOL_L", 0x1F801D82: "SPU_MAIN_VOL_R", 0x1F801DAA: "SPU_CTRL", 0x1F801DAE: "SPU_STAT",
}

// HWName devolve o nome do registrador de hardware em addr, ou "" se não for conhecido.
func HWName(addr uint32) string {
	a := addr & 0x1FFFFFFF
	if a < 0x1F801000 || a >= 0x1F803000 {
		return ""
	}
	if n, ok := hwFixed[a]; ok {
		return n
	}
	switch {
	case a >= 0x1F801080 && a < 0x1F8010F0: // 7 canais de DMA, 0x10 bytes cada
		ch := (a - 0x1F801080) / 0x10
		return fmt.Sprintf("DMA%d_%s_%s", ch, dmaChannel[ch], [4]string{"MADR", "BCR", "CHCR", "?"}[(a&0xF)/4])
	case a >= 0x1F801100 && a < 0x1F801130: // 3 timers
		t := (a - 0x1F801100) / 0x10
		return fmt.Sprintf("TIMER%d_%s", t, [4]string{"COUNT", "MODE", "TARGET", "?"}[(a&0xF)/4])
	case a >= 0x1F801C00 && a < 0x1F801D80: // 24 vozes do SPU
		return fmt.Sprintf("SPU_VOICE%d_+0x%x", (a-0x1F801C00)/0x10, a&0xF)
	}
	return ""
}

// consts acompanha constantes carregadas em registradores (lui/addiu/ori) numa passagem linear.
// É uma aproximação: não segue desvios, então só anota; nunca altera a desmontagem.
type consts struct {
	val [32]uint32
	ok  [32]bool
	// origem de um valor lido de hardware: registrador, máscara já aplicada (andi) e se o rastreio vale
	src     [32]HWAccess
	srcMask [32]uint32
	srcOK   [32]bool

	afterDelay bool // a instrução anterior foi jal/jalr: a próxima é o delay slot

	lastVal uint32 // constante montada pela última instrução addiu/ori
	lastOK  bool

	// globals resolve 'lw rt,off(base)' de uma variável global que o programa inicializa sempre com o mesmo
	// endereço de hardware (padrão do libcd: ponteiros para os registradores do CD-ROM). gsrc guarda de qual
	// global cada registrador foi carregado.
	globals map[uint32]uint32
	gsrc    [32]uint32

	// base de tabela: o registrador vale (constante + índice desconhecido), como em 'addu $at,$at,$idx'
	arr   [32]uint32
	arrOK [32]bool

	// tabela de onde o registrador foi carregado: 'lw rt,off(base indexada)' guarda a base da tabela
	tbl   [32]uint32
	tblOK [32]bool
}

// newConsts cria o rastreador já conhecendo as globais de hardware do executável.
func (e *Exe) newConsts() *consts {
	c := newConsts()
	c.globals = e.hwGlobals()
	return c
}

// newConsts começa com $zero conhecido (0): sem isso 'sw $zero' e 'addiu rt,$zero,k' perderiam o valor.
func newConsts() *consts {
	c := &consts{}
	c.ok[0] = true
	return c
}

// Escritas em $zero são descartadas pelo hardware, então nunca mudam o estado.
func (c *consts) set(r, v uint32) {
	if r != 0 {
		c.val[r], c.ok[r], c.srcOK[r], c.gsrc[r], c.arrOK[r], c.tblOK[r] = v, true, false, 0, false, false
	}
}

func (c *consts) kill(r uint32) {
	if r != 0 {
		c.ok[r], c.srcOK[r], c.gsrc[r], c.arrOK[r], c.tblOK[r] = false, false, 0, false, false
	}
}

// step atualiza o estado e devolve o acesso, se a instrução lê ou escreve um registrador de hardware.
//
// A instrução depois de jal/jalr (delay slot) executa ANTES da chamada, então o efeito da chamada sobre os
// registradores só vale depois dela: 'jal f; addiu $a0,$a0,k' usa o $a0 de antes do jal.
func (c *consts) step(w uint32) (HWAccess, bool) {
	acc, ok := c.stepInner(w)
	// valor que addiu/ori acabou de montar, visível mesmo que a chamada o descarte logo em seguida
	c.lastOK = false
	if op := w >> 26; op == 0x09 || op == 0x0D {
		rt := w >> 16 & 31
		c.lastVal, c.lastOK = c.val[rt], c.ok[rt] && rt != 0
	}
	if c.afterDelay { // w foi o delay slot de uma chamada: agora a chamada clobbera os temporários
		c.afterDelay = false
		for _, r := range []uint32{31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25} {
			c.kill(r)
		}
	}
	if w>>26 == 3 || (w>>26 == 0 && w&0x3F == 0x09) { // jal, jalr
		c.afterDelay = true
	}
	return acc, ok
}

func (c *consts) stepInner(w uint32) (HWAccess, bool) {
	op, rs, rt, rd := w>>26, w>>21&31, w>>16&31, w>>11&31
	imm := int32(int16(w))
	switch {
	case op == 0x0F: // lui
		c.set(rt, w<<16)
	case op == 0x09 || op == 0x08: // addiu/addi
		if c.ok[rs] {
			c.set(rt, c.val[rs]+uint32(imm))
		} else {
			c.kill(rt)
		}
	case op == 0x0C && c.srcOK[rs]: // andi sobre valor lido de hardware: guarda a máscara
		c.src[rt], c.srcMask[rt], c.srcOK[rt] = c.src[rs], c.srcMask[rs]&uint32(uint16(w)), rt != 0
		c.ok[rt] = false
	case op == 0x0D: // ori
		if c.ok[rs] {
			c.set(rt, c.val[rs]|uint32(uint16(w)))
		} else {
			c.kill(rt)
		}
	case op >= 0x20 && op <= 0x26: // loads: escrevem rt, usam rs
		acc, ok := c.access(rs, imm)
		baseOK, baseVal := c.ok[rs], c.val[rs] // antes de kill: rt pode ser o mesmo registrador que rs
		idxOK, idxBase := !c.ok[rs] && c.arrOK[rs], c.arr[rs]
		c.kill(rt)
		if op == 0x23 && idxOK && rt != 0 { // lw de tabela indexada: lembra a base para resolver um jr
			c.tbl[rt], c.tblOK[rt] = idxBase+uint32(imm), true
		}
		if op == 0x23 && baseOK && rt != 0 { // lw de uma global que sempre guarda um endereço de hardware
			if g := baseVal + uint32(imm); c.globals[g] != 0 {
				c.set(rt, c.globals[g])
				c.gsrc[rt] = g
			}
		}
		if mask, sized := map[uint32]uint32{0x20: 0xFF, 0x21: 0xFFFF, 0x23: 0xFFFFFFFF, 0x24: 0xFF, 0x25: 0xFFFF}[op]; ok && sized && rt != 0 {
			c.src[rt], c.srcMask[rt], c.srcOK[rt] = acc, mask, true // valor de hardware: rastreia até o desvio
		}
		return acc, ok
	case op >= 0x28 && op <= 0x2E: // stores: só usam rs; o valor vem de rt
		acc, ok := c.access(rs, imm)
		if ok {
			acc.Store = true
			if width, simple := map[uint32]int{0x28: 1, 0x29: 2, 0x2B: 4}[op]; simple && c.ok[rt] {
				acc.Known, acc.Width = true, width
				acc.Value = c.val[rt]
				if width < 4 {
					acc.Value &= 1<<(8*width) - 1
				}
			}
		}
		return acc, ok
	case op == 0 && (w&0x3F == 0x20 || w&0x3F == 0x21): // add/addu: soma constantes ou marca base de tabela
		okS, okT, vS, vT := c.ok[rs], c.ok[rt], c.val[rs], c.val[rt]
		c.kill(rd)
		switch {
		case okS && okT:
			c.set(rd, vS+vT)
		case okS && looksAddr(vS) && rd != 0:
			c.arr[rd], c.arrOK[rd] = vS, true
		case okT && looksAddr(vT) && rd != 0:
			c.arr[rd], c.arrOK[rd] = vT, true
		}
	case op == 0 && w != 0 && w&0x3F != 0x08 && w&0x3F != 0x18 && w&0x3F != 0x19 && w&0x3F != 0x1A && w&0x3F != 0x1B:
		c.kill(rd) // R-type que escreve rd (jr/mult/div não escrevem)
	case op == 3: // jal: o efeito sobre os registradores vem em step, depois do delay slot
	case op == 0x10 || op == 0x12:
		if rs == 0 || rs == 2 {
			c.kill(rt)
		}
	default:
		if op >= 0x0A && op <= 0x0E { // slti, sltiu, andi, xori
			c.kill(rt)
		}
	}
	return HWAccess{}, false
}

func (c *consts) access(base uint32, off int32) (HWAccess, bool) {
	if !c.ok[base] {
		return HWAccess{}, false
	}
	addr := c.val[base] + uint32(off)
	if n := HWName(addr); n != "" {
		return HWAccess{Name: n, Addr: addr, ViaGlobal: c.gsrc[base]}, true
	}
	return HWAccess{}, false
}

// HWAccess é um acesso a registrador de hardware achado por propagação linear de constantes.
type HWAccess struct {
	Name  string
	Addr  uint32
	PC    uint32
	Store bool   // false: leitura
	Known bool   // escrita com valor constante conhecido (só sb, sh, sw)
	Value uint32 // valor escrito, se Known
	Width int    // bytes escritos, se Known
	// ViaGlobal é o endereço da variável global de onde o ponteiro de hardware foi carregado (0 se o
	// endereço era constante no código). Heurística: vale se o programa só guarda esse valor naquela global.
	ViaGlobal uint32
}

// HWAccesses lista, em ordem, os acessos a registradores de hardware da função em addr (até n instruções).
// É determinístico: serve de fato para o relatório, ao contrário da interpretação do modelo.
func (e *Exe) HWAccesses(addr uint32, n int) []HWAccess {
	var out []HWAccess
	c := e.newConsts()
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		if acc, ok := c.step(w); ok {
			acc.PC = pc
			out = append(out, acc)
		}
	}
	return out
}

// Loop é um desvio para trás dentro da função.
type Loop struct {
	PC, Target    uint32
	Unconditional bool       // j ou beq rX,rX
	Reads         []HWAccess // leituras de hardware dentro do corpo do laço
	Calls         []uint32   // alvos de jal dentro do corpo do laço, sem repetição
	// While e Until descrevem a condição quando o desvio testa um valor lido de hardware, por exemplo
	// "(I_STAT & 0x1) == 0" (repete enquanto) e "(I_STAT & 0x1) != 0" (sai quando). Vazios se não der para saber.
	While, Until string
}

// Polling diz se é uma espera ativa COMPROVADA: laço condicional cuja condição de saída depende de um valor lido
// de hardware (While preenchido). Um laço que apenas lê hardware, mas termina por contador, não é espera ativa.
func (l Loop) Polling() bool { return !l.Unconditional && len(l.Reads) > 0 && l.While != "" }

// ReadsHardware diz se o corpo do laço lê algum registrador de hardware (sem afirmar nada sobre a condição).
func (l Loop) ReadsHardware() bool { return len(l.Reads) > 0 }

// branchCond descreve a condição de um beq/bne contra $zero que testa um valor lido de hardware.
// Devolve {condição de desvio tomado, negação}, por exemplo {"(I_STAT & 0x1) == 0", "(I_STAT & 0x1) != 0"}.
func (c *consts) branchCond(w uint32) ([2]string, bool) {
	op, rs, rt := w>>26, w>>21&31, w>>16&31
	if op != 4 && op != 5 {
		return [2]string{}, false
	}
	r := rs
	if rs == 0 {
		r = rt
	} else if rt != 0 {
		return [2]string{}, false
	}
	if !c.srcOK[r] {
		return [2]string{}, false
	}
	expr := c.src[r].Name
	if m := c.srcMask[r]; m != 0xFFFFFFFF {
		expr = fmt.Sprintf("(%s & 0x%x)", expr, m)
	}
	taken, other := expr+" == 0", expr+" != 0" // beq desvia quando zero
	if op == 5 {
		taken, other = other, taken
	}
	return [2]string{taken, other}, true
}

// Loops devolve os desvios para trás da função em addr. Um laço condicional que lê um registrador de
// hardware é uma espera ativa: o código só sai quando o registrador muda.
func (e *Exe) Loops(addr uint32, n int) []Loop {
	acc := e.HWAccesses(addr, n)
	var out []Loop
	c := e.newConsts()
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		cond, haveCond := c.branchCond(w) // avalia antes de step: o desvio não escreve registradores
		c.step(w)
		op := w >> 26
		var t uint32
		uncond := false
		switch {
		case op == 4 || op == 5 || op == 6 || op == 7 || op == 1:
			t = pc + 4 + uint32(int32(int16(w))<<2)
			uncond = op == 4 && w>>21&31 == w>>16&31
		case op == 2:
			t = (pc+4)&0xF0000000 | (w&0x03FFFFFF)<<2
			uncond = true
		default:
			continue
		}
		if t > pc || t < addr {
			continue
		}
		l := Loop{PC: pc, Target: t, Unconditional: uncond}
		if haveCond && !uncond {
			l.While, l.Until = cond[0], cond[1]
		}
		seen := map[uint32]bool{}
		for off := t; off <= pc; off += 4 {
			if cw, _ := e.Word(off); cw>>26 == 3 {
				if tg := (off+4)&0xF0000000 | (cw&0x03FFFFFF)<<2; !seen[tg] {
					seen[tg] = true
					l.Calls = append(l.Calls, tg)
				}
			}
		}
		for _, a := range acc {
			if !a.Store && a.PC >= t && a.PC <= pc {
				l.Reads = append(l.Reads, a)
			}
		}
		out = append(out, l)
	}
	return out
}

// Indirects devolve os endereços de saltos cujo destino não é estático (jr que não seja $ra, e jalr)
// da função em addr (até n instruções, como em DisasmRange). Ficam como "desconhecidos" na análise.
func (e *Exe) Indirects(addr uint32, n int) []uint32 {
	var out []uint32
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		if w>>26 == 0 && ((w&0x3F == 0x08 && w>>21&31 != 31) || w&0x3F == 0x09) {
			out = append(out, pc)
		}
	}
	return out
}

// hwGlobals procura variáveis globais que guardam um endereço de hardware, por exemplo o ponteiro para
// CDROM_INDEX: ou o código guarda (sw) sempre o mesmo valor nelas, ou o dado já vem preenchido na imagem do
// executável (.data). Descarta globais com valores diferentes ou com escritas de valor desconhecido. É uma
// heurística linear: aliasing por ponteiros e alteração em tempo de execução não são considerados.
func (e *Exe) hwGlobals() map[uint32]uint32 {
	e.gonce.Do(func() {
		vals := map[uint32]uint32{}
		bad := map[uint32]bool{}
		starts := e.callTargets()
		c := newConsts()
		resetAt := -1
		for off, i := 0, 0; off+4 <= len(e.Text); off, i = off+4, i+1 {
			pc := e.Load + uint32(off)
			if _, isStart := starts[pc]; isStart || i == resetAt {
				c = newConsts() // não deixa constantes de uma função vazarem para a seguinte
			}
			w := le.Uint32(e.Text[off:])
			if w>>26 == 0x2B && c.ok[w>>21&31] { // sw com base constante
				addr := c.val[w>>21&31] + uint32(int32(int16(w)))
				if HWName(addr) == "" && addr&0x1FFFFFFF < 0x00200000 {
					rt := w >> 16 & 31
					switch v, seen := vals[addr]; {
					case !c.ok[rt]:
						bad[addr] = true
					case seen && v != c.val[rt]:
						bad[addr] = true
					default:
						vals[addr] = c.val[rt]
					}
				}
			}
			c.step(w)
			if op := w >> 26; op == 2 || (op == 0 && w&0x3F == 0x08) {
				resetAt = i + 2 // depois do delay slot
			}
		}
		// Dados iniciais da própria imagem (como .data): um ponteiro já preenchido com um endereço de hardware.
		// Vale se o código não o sobrescreve com valor diferente ou desconhecido.
		for off := 0; off+4 <= len(e.Text); off += 4 {
			addr := e.Load + uint32(off)
			v := le.Uint32(e.Text[off:])
			if HWName(v) == "" || bad[addr] {
				continue
			}
			if old, seen := vals[addr]; seen && old != v {
				bad[addr] = true
				continue
			}
			vals[addr] = v
		}
		e.globals = map[uint32]uint32{}
		for a, v := range vals {
			if !bad[a] && HWName(v) != "" {
				e.globals[a] = v
			}
		}
	})
	return e.globals
}

// GlobalPointers devolve as globais de hardware resolvidas (global -> endereço de hardware).
func (e *Exe) GlobalPointers() map[uint32]uint32 { return e.hwGlobals() }

// looksAddr descarta constantes pequenas, que quase nunca são o início de uma tabela.
func looksAddr(v uint32) bool { return v&0x1FFFFFFF >= 0x10000 }

// effective calcula o endereço efetivo de um acesso 'off(rs)': constante, ou base de tabela com índice variável.
func (c *consts) effective(rs uint32, off int32) (addr uint32, indexed, ok bool) {
	switch {
	case c.ok[rs]:
		return c.val[rs] + uint32(off), false, true
	case c.arrOK[rs]:
		return c.arr[rs] + uint32(off), true, true
	}
	return 0, false, false
}

// JumpTable é um 'jr' que salta por uma tabela de endereços indexada (switch).
type JumpTable struct {
	PC      uint32   // o jr
	Base    uint32   // início da tabela na imagem
	Targets []uint32 // destinos lidos da imagem
}

// JumpTables resolve os 'jr' (que não são $ra) da função em addr que saltam por uma tabela indexada de base
// constante, lendo da imagem as entradas que apontam para dentro da função. Heurística: a tabela é lida até a
// primeira palavra que não aponta para dentro da função (ou 64 entradas); tabelas de ponteiros para outras
// funções (vtables) não são resolvidas.
func (e *Exe) JumpTables(addr uint32, n int) []JumpTable {
	var out []JumpTable
	c := e.newConsts()
	end := addr + uint32(e.span(addr, n))*4
	for i, last := 0, e.span(addr, n); i < last; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		if w>>26 == 0 && w&0x3F == 0x08 && w>>21&31 != 31 && c.tblOK[w>>21&31] {
			jt := JumpTable{PC: pc, Base: c.tbl[w>>21&31]}
			for k := uint32(0); k < 64; k++ {
				v, ok := e.Word(jt.Base + 4*k)
				if !ok || v < addr || v >= end || v%4 != 0 {
					break
				}
				jt.Targets = append(jt.Targets, v)
			}
			if len(jt.Targets) > 0 {
				out = append(out, jt)
			}
		}
		c.step(w)
	}
	return out
}
