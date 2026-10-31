# exemplo10: setter de callback (a global é chamada por jalr) e setter de nível (a global nunca é chamada).
# Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	swap_cb
	addiu	$a0, $zero, 1
	jal	fire
	nop
	jal	swap_lvl
	addiu	$a0, $zero, 2
1:	j	1b
	nop

swap_cb:
	lui	$v1, %hi(cb)
	lw	$v0, %lo(cb)($v1)
	jr	$ra
	sw	$a0, %lo(cb)($v1)

fire:
	lui	$t0, %hi(cb)
	lw	$t1, %lo(cb)($t0)
	nop
	jalr	$t1
	nop
	jr	$ra
	nop

swap_lvl:
	lui	$v1, %hi(lvl)
	lw	$v0, %lo(lvl)($v1)
	jr	$ra
	sw	$a0, %lo(lvl)($v1)

	.align	2
cb:
	.word	0
lvl:
	.word	0
