// Package ps1 lê executáveis PS-X EXE do PlayStation 1 e desmonta MIPS R3000.
package ps1

import (
	"encoding/binary"
	"errors"
	"sort"
	"sync"
)

const headerSize = 0x800

// Exe é um PS-X EXE já carregado em memória.
type Exe struct {
	PC, GP, Load, SP uint32
	Region           string
	Text             []byte // segmento de código/dados, começa em Load

	once  sync.Once
	calls map[uint32]int // alvo de jal -> número de chamadas; inclui a entrada

	gonce   sync.Once
	globals map[uint32]uint32 // variável global -> endereço de hardware que o programa sempre guarda nela
}

var le = binary.LittleEndian

// IsExe diz se os bytes começam com o cabeçalho PS-X EXE.
func IsExe(b []byte) bool { return len(b) >= headerSize && string(b[:8]) == "PS-X EXE" }

func ParseExe(b []byte) (*Exe, error) {
	if !IsExe(b) {
		return nil, errors.New("não é um PS-X EXE (cabeçalho ausente ou arquivo menor que 0x800)")
	}
	size := le.Uint32(b[0x1C:])
	if avail := uint32(len(b) - headerSize); size > avail {
		size = avail // arquivo truncado: usa o que existe
	}
	region := b[0x4C:headerSize]
	for i, c := range region {
		if c == 0 {
			region = region[:i]
			break
		}
	}
	return &Exe{
		PC: le.Uint32(b[0x10:]), GP: le.Uint32(b[0x14:]), Load: le.Uint32(b[0x18:]), SP: le.Uint32(b[0x30:]),
		Region: string(region), Text: b[headerSize : headerSize+size],
	}, nil
}

// Word lê a instrução no endereço virtual addr.
func (e *Exe) Word(addr uint32) (uint32, bool) {
	if addr < e.Load || addr%4 != 0 || uint64(addr-e.Load)+4 > uint64(len(e.Text)) {
		return 0, false
	}
	return le.Uint32(e.Text[addr-e.Load:]), true
}

// Func é um candidato a função: alvo de algum jal.
type Func struct {
	Addr  uint32
	Calls int
}

// callTargets varre o código uma vez atrás de 'jal' (alvos de chamada são confiáveis, ao contrário de prólogos).
func (e *Exe) callTargets() map[uint32]int {
	e.once.Do(func() {
		e.calls = map[uint32]int{e.PC: 0}
		for off := 0; off+4 <= len(e.Text); off += 4 {
			w := le.Uint32(e.Text[off:])
			if w>>26 != 3 {
				continue
			}
			pc := e.Load + uint32(off)
			t := (pc+4)&0xF0000000 | (w&0x03FFFFFF)<<2
			if t >= e.Load && t < e.Load+uint32(len(e.Text)) {
				e.calls[t]++
			}
		}
	})
	return e.calls
}

// FindFunctions devolve os candidatos a função, os mais chamados primeiro. O ponto de entrada sempre entra.
// Funções só alcançadas por jalr ou tabelas de salto não aparecem.
func (e *Exe) FindFunctions() []Func {
	counts := e.callTargets()
	out := make([]Func, 0, len(counts))
	for a, c := range counts {
		out = append(out, Func{a, c})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Calls != out[j].Calls {
			return out[i].Calls > out[j].Calls
		}
		return out[i].Addr < out[j].Addr
	})
	return out
}

// Callers devolve os endereços das instruções 'jal' que chamam target, em ordem crescente.
func (e *Exe) Callers(target uint32) []uint32 {
	var out []uint32
	for off := 0; off+4 <= len(e.Text); off += 4 {
		w := le.Uint32(e.Text[off:])
		if w>>26 != 3 {
			continue
		}
		pc := e.Load + uint32(off)
		if (pc+4)&0xF0000000|(w&0x03FFFFFF)<<2 == target {
			out = append(out, pc)
		}
	}
	return out
}

// NearestStart devolve o início de função conhecido (alvo de jal ou entrada) mais próximo antes de pc.
// É só uma aproximação: funções alcançadas apenas por tabela de salto ou jalr não são conhecidas, e
// então pc pode pertencer a uma função desconhecida logo depois do início devolvido.
func (e *Exe) NearestStart(pc uint32) (uint32, bool) {
	var best uint32
	found := false
	for a := range e.callTargets() {
		if a <= pc && (!found || a > best) {
			best, found = a, true
		}
	}
	return best, found
}

// CallCount diz quantas chamadas diretas (jal) a função em addr recebe; ok é false se addr não é início
// de função conhecido.
func (e *Exe) CallCount(addr uint32) (calls int, ok bool) {
	calls, ok = e.callTargets()[addr]
	return
}

// StringAt devolve a string ASCII (≥4 caracteres, legível) que começa em addr dentro da imagem.
func (e *Exe) StringAt(addr uint32) (string, bool) { return e.asciiAt(addr) }
