# exemplo9: instaladores de callback (trocam o ponteiro global e devolvem o antigo), uma função que só grava, e
# strings: uma parecida com identificador (nome de depuração) e outras que não são. Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	swap_a
	addiu	$a0, $zero, 1
	jal	swap_b
	addiu	$a0, $zero, 2
	jal	only_set
	addiu	$a0, $zero, 3
	jal	ident
	nop
	jal	noident
	nop
1:	j	1b
	nop

swap_a:
	lui	$v1, %hi(cb_a)
	lw	$v0, %lo(cb_a)($v1)
	jr	$ra
	sw	$a0, %lo(cb_a)($v1)

swap_b:
	lui	$v1, %hi(cb_b)
	lw	$v0, %lo(cb_b)($v1)
	nop
	jr	$ra
	sw	$a0, %lo(cb_b)($v1)

only_set:
	lui	$v1, %hi(cb_a)
	jr	$ra
	sw	$a0, %lo(cb_a)($v1)

ident:
	lui	$a0, %hi(nm_ident)
	jr	$ra
	addiu	$a0, $a0, %lo(nm_ident)

noident:
	lui	$a0, %hi(nm_text)
	jr	$ra
	addiu	$a0, $a0, %lo(nm_text)

	.align	2
cb_a:
	.word	0
cb_b:
	.word	0
nm_ident:
	.asciz	"CD_sync"
nm_text:
	.asciz	"hello world foo"
