// Decompila uma função (nome ou endereço passado como primeiro argumento).
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class Decompile extends GhidraScript {
	@Override
	public void run() throws Exception {
		String want = getScriptArgs()[0];
		DecompInterface ifc = new DecompInterface();
		ifc.openProgram(currentProgram);
		for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
			if (f.getName().equals(want) || f.getEntryPoint().toString().equals(want)) {
				println(ifc.decompileFunction(f, 60, monitor).getDecompiledFunction().getC());
				return;
			}
		}
		println("função não encontrada: " + want);
	}
}
