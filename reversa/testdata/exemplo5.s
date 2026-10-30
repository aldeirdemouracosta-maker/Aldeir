# exemplo5: ponteiros de hardware guardados em variáveis globais, uma global ambígua e uma string de formato.
# Imita o padrão do libcd. Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	init
	nop
	jal	send_cmd
	addiu	$a0, $zero, 2
	jal	send_cmd
	addiu	$a0, $zero, 0xe
	jal	use_conflict
	nop
1:	j	1b
	nop

init:
	lui	$t0, 0x1f80
	lui	$t2, 0x8002
	addiu	$t1, $t0, 0x1800
	sw	$t1, 0x10($t2)
	addiu	$t1, $t0, 0x1801
	sw	$t1, 0x14($t2)
	addiu	$t1, $t0, 0x1800
	sw	$t1, 0x20($t2)
	addiu	$t1, $t0, 0x1801
	sw	$t1, 0x20($t2)
	jr	$ra
	nop

send_cmd:
	lui	$t2, 0x8002
	lw	$t3, 0x10($t2)
	nop
	sb	$zero, 0($t3)
	lw	$t4, 0x14($t2)
	nop
	sb	$a0, 0($t4)
	jr	$ra
	nop

use_conflict:
	lui	$t2, 0x8002
	lw	$t3, 0x20($t2)
	lui	$a0, %hi(fmt)
	sb	$zero, 0($t3)
	jr	$ra
	addiu	$a0, $a0, %lo(fmt)

fmt:
	.asciz	"CD_cw: %s\n"
	.align	2
