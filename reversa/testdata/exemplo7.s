# exemplo7: callback instalado e disparado por jalr, flag de estado e tabela acessada por índice.
# Imita o padrão do libcd. Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	set_cb
	addiu	$a0, $zero, 0x1234
	jal	fire
	nop
	jal	set_flag
	nop
	jal	wait_flag
	nop
	jal	lookup
	addiu	$a0, $zero, 2
1:	j	1b
	nop

set_cb:
	lui	$t0, %hi(cb_ptr)
	jr	$ra
	sw	$a0, %lo(cb_ptr)($t0)

fire:
	lui	$t0, %hi(cb_ptr)
	lw	$t1, %lo(cb_ptr)($t0)
	nop
	jalr	$t1
	nop
	jr	$ra
	nop

set_flag:
	lui	$t0, %hi(flag)
	addiu	$t1, $zero, 5
	jr	$ra
	sb	$t1, %lo(flag)($t0)

wait_flag:
	lui	$t0, %hi(flag)
1:	lbu	$t1, %lo(flag)($t0)
	nop
	beq	$t1, $zero, 1b
	nop
	jr	$ra
	nop

lookup:
	sll	$a0, $a0, 2
	lui	$at, %hi(table)
	addu	$at, $at, $a0
	lw	$v0, %lo(table)($at)
	jr	$ra
	nop

	.align	2
cb_ptr:
	.word	0
flag:
	.byte	0
	.align	2
table:
	.word	0x10, 0x20, 0x30
