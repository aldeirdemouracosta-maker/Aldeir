package orchestrator

import (
	"context"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"sync/atomic"

	"reversa/internal/evidence"
	"reversa/internal/llm"
	"reversa/internal/ps1"
)

// PS1 é o pipeline em três estágios:
//  1. triagem determinística em Go (sem modelo): cabeçalho, funções candidatas, desmontagem;
//  2. operários: um modelo pequeno resume cada função, em paralelo;
//  3. sintetizador: um modelo maior junta tudo, citando evidências.
//
// Fatos (saída das ferramentas) e hipóteses (texto do modelo) ficam em registros separados.
type PS1 struct {
	Worker      llm.Chatter // modelo pequeno e rápido
	Synthesizer llm.Chatter // modelo maior, uma única chamada
	Evidence    *evidence.Log
	Workers     int
	TopN        int // quantas funções analisar
	MaxInsns    int // instruções por função enviadas ao modelo
	// Progress, se definido, recebe uma linha a cada marco (estágios e funções concluídas).
	Progress func(format string, args ...any)
}

func (p *PS1) logf(format string, args ...any) {
	if p.Progress != nil {
		p.Progress(format, args...)
	}
}

const workerPrompt = `Código MIPS R3000 (PlayStation 1) de uma função.%s
Responda em no máximo 2 frases, em português, com o propósito provável da função. Use os nomes de
registradores de hardware e os endereços como aparecem no código (após ';'); não recalcule nem converta números.
Não liste registradores nem instruções. Não invente símbolos. Se não der para saber, diga "indeterminado".

%s`

func (p *PS1) Run(ctx context.Context, exe *ps1.Exe) (string, error) {
	// Estágio 1: fatos.
	header := fmt.Sprintf("entrada=0x%08x carga=0x%08x gp=0x%08x sp=0x%08x região=%q tamanho=%d bytes",
		exe.PC, exe.Load, exe.GP, exe.SP, exe.Region, len(exe.Text))
	hdr := p.Evidence.AddAs(evidence.Observed, "ps1_header", "", header, "Lido do cabeçalho PS-X EXE; o conteúdo não é validado.")

	funcs := exe.FindFunctions()
	totalFuncs := len(funcs)
	if p.TopN > 0 && len(funcs) > p.TopN {
		funcs = funcs[:p.TopN]
	}
	type job struct {
		context string
		stub    string // não vazio: stub de BIOS ou de syscall, sem lógica própria; o modelo não é consultado
		fn      ps1.Func
		dis     string
		ev      int
		unknown int // id da evidência de saltos indiretos, 0 se não houver
	}
	jobs := make([]job, len(funcs))
	for i, f := range funcs {
		dis := exe.DisasmRange(f.Addr, p.MaxInsns)
		rec := p.Evidence.AddAs(evidence.Derived, "ps1_disasm", fmt.Sprintf("0x%08x (%s)", f.Addr, role(exe, f)), dis,
			"Desmontagem linear; chamadas indiretas (jalr) e dados no meio do código não são resolvidos.")
		jobs[i] = job{fn: f, dis: dis, ev: rec.ID, context: funcContext(exe, f, p.MaxInsns)}
		jobs[i].stub = stubKind(exe, f.Addr)
		if ind := unresolved(exe, f.Addr, p.MaxInsns); len(ind) > 0 {
			var list strings.Builder
			for _, pc := range ind {
				fmt.Fprintf(&list, "0x%08x ", pc)
			}
			u := p.Evidence.AddAs(evidence.Unknown, "ps1_indirect", fmt.Sprintf("0x%08x", f.Addr), strings.TrimSpace(list.String()),
				"Destino de jr/jalr não é estático; a análise não sabe para onde esses saltos vão.")
			jobs[i].unknown = u.ID
		}
	}

	// Estágio 2: hipóteses em paralelo.
	p.logf("estágio 1/3 concluído: %d funções; resumindo com o modelo pequeno (%d em paralelo)", len(jobs), max(p.Workers, 1))
	var done atomic.Int32
	res := Map(ctx, jobs, p.Workers, func(ctx context.Context, j job) (string, error) {
		if j.stub != "" {
			p.logf("estágio 2/3: %d/%d funções resumidas (0x%08x: stub, sem modelo)", done.Add(1), len(jobs), j.fn.Addr)
			return "", nil
		}
		m, err := p.Worker.Chat(ctx, []llm.Message{{Role: "user", Content: fmt.Sprintf(workerPrompt, j.context, j.dis)}}, nil)
		p.logf("estágio 2/3: %d/%d funções resumidas (0x%08x)", done.Add(1), len(jobs), j.fn.Addr)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(m.Content), nil
	})

	// Os fatos de cada função vêm do programa; o modelo só escreve o resumo geral. Assim as citações [E#] e os
	// registradores de hardware nunca dependem de o modelo copiar números corretamente.
	var body, forModel strings.Builder
	fmt.Fprintf(&body, "## Fatos\n\n- Cabeçalho [E%d] (observado): %s\n", hdr.ID, header)
	fmt.Fprintf(&body, "- Cobertura: %d de %d funções achadas por chamada direta (jal) foram analisadas. Funções chamadas só por jalr ou por tabela de salto não são achadas.\n\n## Funções\n", len(jobs), totalFuncs)
	fmt.Fprintf(&forModel, "Cabeçalho: %s\n\nFunções analisadas:\n", header)
	for i, r := range res {
		j := jobs[i]
		fmt.Fprintf(&body, "\n### 0x%08x (%s)\n\n- Desmontagem: [E%d] (derivada)\n", j.fn.Addr, role(exe, j.fn), j.ev)
		if j.stub != "" {
			fmt.Fprintf(&body, "- Tipo (derivado): %s\n", j.stub)
		}
		if exe.Recursive(j.fn.Addr, p.MaxInsns) {
			fmt.Fprintf(&body, "- Recursão (derivado): chama a si mesma\n")
		}
		if jt := jumpTableFacts(exe.JumpTables(j.fn.Addr, p.MaxInsns)); jt != "" {
			fmt.Fprintf(&body, "- Tabelas de salto (derivado): %s\n", jt)
		}
		if hw := hwFacts(exe.HWAccesses(j.fn.Addr, p.MaxInsns)); hw != "" {
			fmt.Fprintf(&body, "- Hardware tocado (derivado): %s\n", hw)
		}
		if lp := loopFacts(exe.Loops(j.fn.Addr, p.MaxInsns)); lp != "" {
			fmt.Fprintf(&body, "- Laços (derivado): %s\n", lp)
		}
		if st := stringFacts(exe.StringRefs(j.fn.Addr, p.MaxInsns)); st != "" {
			fmt.Fprintf(&body, "- Strings referenciadas (derivado): %s\n", st)
		}
		if exe.Truncated(j.fn.Addr, p.MaxInsns) {
			fmt.Fprintf(&body, "- Aviso: análise truncada em %d instruções (-insns); a função continua\n", p.MaxInsns)
		}
		if cs := exe.Callees(j.fn.Addr, p.MaxInsns); len(cs) > 0 {
			fmt.Fprintf(&body, "- Chama: %s\n", hexList(cs))
		}
		if j.unknown != 0 {
			fmt.Fprintf(&body, "- Saltos indiretos sem destino conhecido: %s [E%d] (desconhecido)\n", hexList(unresolved(exe, j.fn.Addr, p.MaxInsns)), j.unknown)
		}
		if j.stub != "" {
			fmt.Fprintf(&body, "- Hipótese do modelo: não solicitada (stub não tem lógica própria)\n")
			fmt.Fprintf(&forModel, "- 0x%08x: %s\n", j.fn.Addr, j.stub)
			continue
		}
		if r.Err != nil {
			fmt.Fprintf(&body, "- Hipótese do modelo: falhou (%v)\n", r.Err)
			continue
		}
		if bad := contradictions(exe, j.fn, r.Val, p.MaxInsns); len(bad) > 0 {
			why := strings.Join(bad, "; ")
			hyp := p.Evidence.AddAs(evidence.Inferred, "llm_hipotese", fmt.Sprintf("0x%08x", j.fn.Addr), r.Val, "Hipótese do modelo; DESCARTADA: contradiz fatos derivados: "+why)
			fmt.Fprintf(&body, "- Hipótese do modelo [E%d] (inferida, DESCARTADA: %s): %s\n", hyp.ID, why, oneLine(r.Val))
			fmt.Fprintf(&forModel, "- 0x%08x (%s): [hipótese do modelo descartada por contradizer fatos; use só os fatos]\n", j.fn.Addr, role(exe, j.fn))
			continue
		}
		hyp := p.Evidence.AddAs(evidence.Inferred, "llm_hipotese", fmt.Sprintf("0x%08x", j.fn.Addr), r.Val, "Hipótese do modelo; não verificada.")
		fmt.Fprintf(&body, "- Hipótese do modelo [E%d] (inferida, não verificada): %s\n", hyp.ID, oneLine(r.Val))
		fmt.Fprintf(&forModel, "- 0x%08x (%s): %s\n", j.fn.Addr, role(exe, j.fn), oneLine(r.Val))
		if j.unknown != 0 {
			fmt.Fprintf(&forModel, "  Atenção: há saltos indiretos não resolvidos; não afirme para onde vão.\n")
		}
	}

	// Estágio 3: resumo geral.
	p.logf("estágio 3/3: escrevendo o resumo geral com o modelo grande (a primeira resposta pode demorar)")
	m, err := p.Synthesizer.Chat(ctx, []llm.Message{
		{Role: "system", Content: "Você é analista de engenharia reversa de PS1. Escreva em português um resumo geral de 4 a 6 linhas sobre o que o programa parece fazer, com base nos resumos das funções. Não cite números de evidência, não liste instruções e não invente endereços ou nomes. Diga o que for incerto."},
		{Role: "user", Content: forModel.String()},
	}, nil)
	if err != nil {
		return "", err
	}
	p.logf("concluído")
	return "# Relatório de engenharia reversa (PS1)\n\n" + body.String() +
		"\n## Resumo geral (hipótese do modelo, não verificada)\n\n" + strings.TrimSpace(m.Content) + "\n", nil
}

// hwFacts descreve cada acesso a hardware como ação ("lê X", "escreve 0x.. em X"), agrupando repetições.
func hwFacts(acc []ps1.HWAccess) string {
	var order []string
	count := map[string]int{}
	for _, a := range acc {
		where := fmt.Sprintf("%s (0x%08x)", a.Name, a.Addr&0x1FFFFFFF)
		var phrase string
		switch {
		case !a.Store:
			phrase = "lê " + where
		case a.Known:
			phrase = fmt.Sprintf("escreve 0x%0*x em %s", a.Width*2, a.Value, where)
		default:
			phrase = "escreve valor variável em " + where
		}
		if a.ViaGlobal != 0 {
			phrase += fmt.Sprintf(" [via ponteiro global 0x%08x]", a.ViaGlobal)
		}
		if count[phrase] == 0 {
			order = append(order, phrase)
		}
		count[phrase]++
	}
	for i, ph := range order {
		if n := count[ph]; n > 1 {
			order[i] += fmt.Sprintf(" ×%d", n)
		}
	}
	return strings.Join(order, "; ")
}

// loopFacts descreve os desvios para trás. Um laço condicional que lê hardware é uma espera ativa (polling);
// quando o programa consegue derivar a condição, ela vai explícita para o modelo não inverter a lógica.
func loopFacts(loops []ps1.Loop) string {
	parts := make([]string, len(loops))
	for i, l := range loops {
		kind := "condicional"
		if l.Unconditional {
			kind = "incondicional"
		}
		parts[i] = fmt.Sprintf("desvio em 0x%08x volta para 0x%08x (%s", l.PC, l.Target, kind)
		if l.ReadsHardware() {
			r := l.Reads[0]
			where := fmt.Sprintf("%s (0x%08x)", r.Name, r.Addr&0x1FFFFFFF)
			if l.Polling() {
				parts[i] += fmt.Sprintf("; espera ativa em %s: repete enquanto %s; sai quando %s", where, l.While, l.Until)
			} else {
				// ler hardware dentro do laço não prova espera ativa: a saída pode ser por contador
				parts[i] += fmt.Sprintf("; lê %s dentro do laço, condição de saída não determinada (não afirmo espera ativa)", where)
			}
		}
		if len(l.Calls) > 0 {
			parts[i] += "; chama dentro do laço: " + hexList(l.Calls)
		}
		parts[i] += ")"
	}
	return strings.Join(parts, "; ")
}

func hexList(addrs []uint32) string {
	parts := make([]string, len(addrs))
	for i, a := range addrs {
		parts[i] = fmt.Sprintf("0x%08x", a)
	}
	return strings.Join(parts, ", ")
}

// oneLine junta a resposta do modelo numa linha para não quebrar a lista do relatório.
func oneLine(s string) string { return strings.Join(strings.Fields(s), " ") }

// role descreve como a função foi achada: o ponto de entrada não é chamado por jal.
func role(exe *ps1.Exe, f ps1.Func) string {
	if f.Addr == exe.PC {
		if f.Calls > 0 {
			return fmt.Sprintf("ponto de entrada, também chamada %dx", f.Calls)
		}
		return "ponto de entrada"
	}
	return fmt.Sprintf("chamada %dx", f.Calls)
}

// funcContext reúne fatos determinísticos que ajudam o modelo: papel da função e o que ela chama.
func funcContext(exe *ps1.Exe, f ps1.Func, maxInsns int) string {
	var b strings.Builder
	if f.Addr == exe.PC {
		b.WriteString(" É o ponto de entrada do programa.")
	}
	if cs := exe.Callees(f.Addr, maxInsns); len(cs) > 0 {
		b.WriteString(" Ela chama:")
		for _, c := range cs {
			fmt.Fprintf(&b, " 0x%08x", c)
		}
		b.WriteString(".")
	}
	// fatos já verificados pelo programa; o modelo errou a lógica de um laço de espera sem isto
	if hw := hwFacts(exe.HWAccesses(f.Addr, maxInsns)); hw != "" {
		fmt.Fprintf(&b, " Fatos verificados (não contradiga): %s.", hw)
	}
	if lp := loopFacts(exe.Loops(f.Addr, maxInsns)); lp != "" {
		fmt.Fprintf(&b, " Laços verificados: %s.", lp)
	}
	if exe.Recursive(f.Addr, maxInsns) {
		b.WriteString(" Recursiva: chama a si mesma.")
	}
	if st := stringFacts(exe.StringRefs(f.Addr, maxInsns)); st != "" {
		fmt.Fprintf(&b, " Strings referenciadas: %s.", st)
	}
	return b.String()
}

func biosName(b ps1.BIOSCall) string {
	return fmt.Sprintf("%c(0x%02x)", 'A'+(b.Table-0xA0)/0x10, b.Func)
}

// stubKind descreve a função se ela for só um stub de BIOS ou de syscall, ou devolve "".
func stubKind(exe *ps1.Exe, addr uint32) string {
	if b, ok := exe.BIOSStub(addr); ok {
		return "stub de chamada à BIOS " + biosName(b)
	}
	if n, ok := exe.SyscallStub(addr); ok {
		// só 1 e 2 têm nome conhecido com certeza (psx-spx); os demais ficam só com o número
		name := map[uint32]string{1: " (EnterCriticalSection)", 2: " (ExitCriticalSection)"}[n]
		return fmt.Sprintf("stub de syscall do kernel com $a0=0x%x%s", n, name)
	}
	return ""
}

var (
	recursivePat = regexp.MustCompile(`(?i)recursiv`)
	addrPat      = regexp.MustCompile(`(?i)0x[0-9a-f]{6,8}`)
)

// contradictions confere a hipótese do modelo contra fatos que o programa já provou. Hipóteses que os
// contradizem são descartadas e não alimentam o resumo geral, para o erro não se propagar.
func contradictions(exe *ps1.Exe, f ps1.Func, text string, maxInsns int) []string {
	var bad []string
	if recursivePat.MatchString(text) && !exe.Recursive(f.Addr, maxInsns) {
		bad = append(bad, "afirma recursão, mas a função não chama a si mesma")
	}
	// endereços citados precisam estar no corpo da função ou entre os fatos derivados dela
	ok := map[uint32]bool{f.Addr: true}
	for off := 0; off < exe.FuncLen(f.Addr, maxInsns); off++ {
		ok[f.Addr+uint32(off)*4] = true
	}
	for _, c := range exe.Callees(f.Addr, maxInsns) {
		ok[c] = true
	}
	for _, a := range exe.HWAccesses(f.Addr, maxInsns) {
		ok[a.Addr], ok[a.Addr&0x1FFFFFFF] = true, true
	}
	for _, l := range exe.Loops(f.Addr, maxInsns) {
		ok[l.PC], ok[l.Target] = true, true
	}
	for _, sr := range exe.StringRefs(f.Addr, maxInsns) {
		ok[sr.Addr] = true
	}
	var strange []string
	seen := map[uint32]bool{}
	for _, m := range addrPat.FindAllString(text, -1) {
		v, err := strconv.ParseUint(m[2:], 16, 32)
		if err != nil || ok[uint32(v)] || seen[uint32(v)] {
			continue
		}
		seen[uint32(v)] = true
		strange = append(strange, m)
	}
	if len(strange) > 0 {
		bad = append(bad, "cita endereço(s) que não aparecem nos fatos da função: "+strings.Join(strange, ", "))
	}
	return bad
}

func stringFacts(refs []ps1.StringRef) string {
	parts := make([]string, len(refs))
	for i, r := range refs {
		parts[i] = fmt.Sprintf("0x%08x %q", r.Addr, r.Text)
	}
	return strings.Join(parts, "; ")
}

// unresolved devolve os saltos indiretos da função que NÃO são um switch por tabela resolvido.
func unresolved(exe *ps1.Exe, addr uint32, maxInsns int) []uint32 {
	resolved := map[uint32]bool{}
	for _, jt := range exe.JumpTables(addr, maxInsns) {
		resolved[jt.PC] = true
	}
	var out []uint32
	for _, pc := range exe.Indirects(addr, maxInsns) {
		if !resolved[pc] {
			out = append(out, pc)
		}
	}
	return out
}

func jumpTableFacts(jts []ps1.JumpTable) string {
	parts := make([]string, len(jts))
	for i, jt := range jts {
		parts[i] = fmt.Sprintf("jr em 0x%08x salta pela tabela 0x%08x com %d destinos: %s", jt.PC, jt.Base, len(jt.Targets), hexList(jt.Targets))
	}
	return strings.Join(parts, "; ")
}
