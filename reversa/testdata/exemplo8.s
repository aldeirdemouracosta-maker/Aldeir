# exemplo8: switch por tabela de salto (jr por tabela indexada) e um laço de leitura limitada de hardware.
# Imita o padrão da rotina de interrupção do CD. Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	sw_fn
	addiu	$a0, $zero, 1
	jal	bounded
	nop
1:	j	1b
	nop

sw_fn:
	sltiu	$v0, $a0, 3
	beq	$v0, $zero, sw_def
	sll	$a0, $a0, 2
	lui	$at, %hi(sw_tbl)
	addu	$at, $at, $a0
	lw	$v0, %lo(sw_tbl)($at)
	nop
	jr	$v0
	nop
sw_c0:
	addiu	$v0, $zero, 10
	j	sw_end
	nop
sw_c1:
	addiu	$v0, $zero, 20
	j	sw_end
	nop
sw_c2:
	addiu	$v0, $zero, 30
	j	sw_end
	nop
sw_def:
	addiu	$v0, $zero, -1
sw_end:
	jr	$ra
	nop

# lê o registrador de índice do CD até 8 vezes: a condição do laço é o contador, não o hardware
bounded:
	lui	$t0, 0x1f80
	addu	$s0, $zero, $zero
2:	lbu	$t1, 0x1800($t0)
	addiu	$s0, $s0, 1
	slti	$v0, $s0, 8
	bne	$v0, $zero, 2b
	nop
	jr	$ra
	nop

	.align	2
sw_tbl:
	.word	sw_c0, sw_c1, sw_c2
