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
}

func (c *consts) set(r, v uint32) { c.val[r], c.ok[r] = v, true }
func (c *consts) kill(r uint32)   { c.ok[r] = false }

// step atualiza o estado e devolve o acesso, se a instrução lê ou escreve um registrador de hardware.
func (c *consts) step(w uint32) (HWAccess, bool) {
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
	case op == 0x0D: // ori
		if c.ok[rs] {
			c.set(rt, c.val[rs]|uint32(uint16(w)))
		} else {
			c.kill(rt)
		}
	case op >= 0x20 && op <= 0x26: // loads: escrevem rt, usam rs
		acc, ok := c.access(rs, imm)
		c.kill(rt)
		return acc, ok
	case op >= 0x28 && op <= 0x2E: // stores: só usam rs
		return c.access(rs, imm)
	case op == 0 && w != 0 && w&0x3F != 0x08 && w&0x3F != 0x18 && w&0x3F != 0x19 && w&0x3F != 0x1A && w&0x3F != 0x1B:
		c.kill(rd) // R-type que escreve rd (jr/mult/div não escrevem)
	case op == 3: // jal clobbera $ra e, por convenção, os temporários
		for _, r := range []uint32{31, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25} {
			c.kill(r)
		}
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
		return HWAccess{Name: n, Addr: addr}, true
	}
	return HWAccess{}, false
}

// HWAccess é um acesso a registrador de hardware achado por propagação linear de constantes.
type HWAccess struct {
	Name string
	Addr uint32
	PC   uint32
}

// HWAccesses lista, em ordem, os acessos a registradores de hardware da função em addr (até n instruções).
// É determinístico: serve de fato para o relatório, ao contrário da interpretação do modelo.
func (e *Exe) HWAccesses(addr uint32, n int) []HWAccess {
	var out []HWAccess
	var c consts
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
