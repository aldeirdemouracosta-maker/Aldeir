// Lista funções: endereço, tamanho e nome.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class ListFunctions extends GhidraScript {
	@Override
	public void run() throws Exception {
		for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
			println(f.getEntryPoint() + " " + f.getBody().getNumAddresses() + " " + f.getName());
		}
	}
}
