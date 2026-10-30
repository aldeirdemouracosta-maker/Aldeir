package ps1

import (
	"fmt"
	"strings"
)

var reg = [32]string{"zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
	"s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"}

var rtype = map[uint32]string{0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu", 0x24: "and", 0x25: "or",
	0x26: "xor", 0x27: "nor", 0x2A: "slt", 0x2B: "sltu", 0x04: "sllv", 0x06: "srlv", 0x07: "srav"}

var itype = map[uint32]string{0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori"}

var mem = map[uint32]string{0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x26: "lwr",
	0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2E: "swr", 0x32: "lwc2", 0x3A: "swc2"}

// hex16 imprime um deslocamento ou imediato com sinal em hexadecimal (0x1070, -0x8). Decimal confunde
// quem lê (e os modelos): 4256 é 0x10a0, não "0x4256".
func hex16(v int32) string {
	if v < 0 {
		return fmt.Sprintf("-0x%x", -v)
	}
	return fmt.Sprintf("0x%x", v)
}

// Disasm devolve uma instrução MIPS R3000 em texto. pc é o endereço da instrução.
func Disasm(w, pc uint32) string {
	op, rs, rt, rd := w>>26, w>>21&31, w>>16&31, w>>11&31
	sh, fn := w>>6&31, w&63
	imm := int16(w)
	br := pc + 4 + uint32(int32(imm)<<2)
	switch {
	case w == 0:
		return "nop"
	case op == 0:
		if n, ok := rtype[fn]; ok {
			if fn >= 0x04 && fn <= 0x07 {
				return fmt.Sprintf("%s $%s,$%s,$%s", n, reg[rd], reg[rt], reg[rs])
			}
			return fmt.Sprintf("%s $%s,$%s,$%s", n, reg[rd], reg[rs], reg[rt])
		}
		switch fn {
		case 0x00, 0x02, 0x03:
			return fmt.Sprintf("%s $%s,$%s,%d", map[uint32]string{0: "sll", 2: "srl", 3: "sra"}[fn], reg[rd], reg[rt], sh)
		case 0x08:
			return "jr $" + reg[rs]
		case 0x09:
			return fmt.Sprintf("jalr $%s,$%s", reg[rd], reg[rs])
		case 0x0C:
			return fmt.Sprintf("syscall 0x%x", w>>6&0xFFFFF)
		case 0x0D:
			return fmt.Sprintf("break 0x%x", w>>6&0xFFFFF)
		case 0x10, 0x12:
			return fmt.Sprintf("%s $%s", map[uint32]string{0x10: "mfhi", 0x12: "mflo"}[fn], reg[rd])
		case 0x11, 0x13:
			return fmt.Sprintf("%s $%s", map[uint32]string{0x11: "mthi", 0x13: "mtlo"}[fn], reg[rs])
		case 0x18, 0x19, 0x1A, 0x1B:
			return fmt.Sprintf("%s $%s,$%s", map[uint32]string{0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu"}[fn], reg[rs], reg[rt])
		}
	case op == 1:
		n := map[uint32]string{0: "bltz", 1: "bgez", 16: "bltzal", 17: "bgezal"}[rt]
		if n != "" {
			return fmt.Sprintf("%s $%s,0x%08x", n, reg[rs], br)
		}
	case op == 2 || op == 3:
		return fmt.Sprintf("%s 0x%08x", map[uint32]string{2: "j", 3: "jal"}[op], (pc+4)&0xF0000000|(w&0x03FFFFFF)<<2)
	case op == 4 || op == 5:
		return fmt.Sprintf("%s $%s,$%s,0x%08x", map[uint32]string{4: "beq", 5: "bne"}[op], reg[rs], reg[rt], br)
	case op == 6 || op == 7:
		return fmt.Sprintf("%s $%s,0x%08x", map[uint32]string{6: "blez", 7: "bgtz"}[op], reg[rs], br)
	case itype[op] != "":
		if op == 0x0C || op == 0x0D || op == 0x0E {
			return fmt.Sprintf("%s $%s,$%s,0x%x", itype[op], reg[rt], reg[rs], uint16(w))
		}
		return fmt.Sprintf("%s $%s,$%s,%s", itype[op], reg[rt], reg[rs], hex16(int32(imm)))
	case op == 0x0F:
		return fmt.Sprintf("lui $%s,0x%x", reg[rt], uint16(w))
	case mem[op] != "":
		return fmt.Sprintf("%s $%s,%s($%s)", mem[op], reg[rt], hex16(int32(imm)), reg[rs])
	case op == 0x10:
		switch rs {
		case 0:
			return fmt.Sprintf("mfc0 $%s,$%d", reg[rt], rd)
		case 4:
			return fmt.Sprintf("mtc0 $%s,$%d", reg[rt], rd)
		case 16:
			return "rfe"
		}
	case op == 0x12:
		return fmt.Sprintf("cop2 0x%07x ; GTE", w&0x1FFFFFF)
	}
	return fmt.Sprintf(".word 0x%08x", w)
}

// span devolve quantas instruções (no máximo n) vão de addr até o fim provável da função.
//
// A função termina após um salto incondicional (jr, j ou b) e seu delay slot, a menos que algum desvio
// anterior aponte para depois dele (retorno antecipado, if/else). Também termina onde começa outra função
// (alvo de jal). É uma heurística: tabelas de salto e funções sem retorno podem enganá-la.
func (e *Exe) span(addr uint32, n int) int {
	starts := e.callTargets()
	var pending uint32 // maior alvo de desvio para frente visto até aqui
	for i := 0; i < n; i++ {
		pc := addr + uint32(i)*4
		w, ok := e.Word(pc)
		if !ok {
			return i
		}
		if _, isStart := starts[pc]; isStart && i > 0 {
			return i
		}
		op := w >> 26
		unconditional := false
		switch {
		case op == 4 || op == 5 || op == 6 || op == 7 || op == 1: // beq bne blez bgtz regimm
			if t := pc + 4 + uint32(int32(int16(w))<<2); t > pending {
				pending = t
			}
			unconditional = op == 4 && w>>21&31 == w>>16&31 // beq rX,rX: desvio incondicional
		case op == 2: // j
			if t := (pc+4)&0xF0000000 | (w&0x03FFFFFF)<<2; t > pc && t > pending {
				pending = t
			}
			unconditional = true
		case op == 0 && w&0x3F == 0x08: // jr
			unconditional = true
		}
		if unconditional && pending < pc+8 {
			return min(i+2, n) // inclui o delay slot
		}
	}
	return n
}

// Callees devolve, em ordem de aparição e sem repetição, os alvos de jal dentro da função em addr.
func (e *Exe) Callees(addr uint32, n int) []uint32 {
	var out []uint32
	seen := map[uint32]bool{}
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		if w>>26 != 3 {
			continue
		}
		if t := (pc+4)&0xF0000000 | (w&0x03FFFFFF)<<2; !seen[t] {
			seen[t] = true
			out = append(out, t)
		}
	}
	return out
}

// DisasmRange desmonta a função em addr, até n instruções, parando após 'jr $ra' e seu delay slot.
func (e *Exe) DisasmRange(addr uint32, n int) string {
	var b strings.Builder
	c := e.newConsts()
	for i, end := 0, e.span(addr, n); i < end; i++ {
		pc := addr + uint32(i)*4
		w, _ := e.Word(pc)
		line := fmt.Sprintf("%08x  %08x  %s", pc, w, Disasm(w, pc))
		if hw, ok := c.step(w); ok {
			line += fmt.Sprintf("  ; %s (0x%08x)", hw.Name, hw.Addr&0x1FFFFFFF) // endereço físico: iguala KSEG0/KSEG1
			if hw.ViaGlobal != 0 {
				line += fmt.Sprintf(" via ponteiro global 0x%08x", hw.ViaGlobal)
			}
		}
		b.WriteString(line + "\n")
	}
	return b.String()
}

// Truncated diz se a função em addr continua além de n instruções (o fim não foi alcançado).
func (e *Exe) Truncated(addr uint32, n int) bool { return e.span(addr, n+1) == n+1 }
