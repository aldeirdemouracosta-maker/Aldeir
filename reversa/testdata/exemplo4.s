# exemplo4: stubs de syscall do kernel (padrão: addiu $a0,$zero,N; syscall; jr $ra). Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	sys_enter
	nop
	jal	sys_exit
	nop
1:	j	1b
	nop

sys_enter:
	addiu	$a0, $zero, 1
	syscall	0
	jr	$ra
	nop

sys_exit:
	addiu	$a0, $zero, 2
	syscall	0
	jr	$ra
	nop
