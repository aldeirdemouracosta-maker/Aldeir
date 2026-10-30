# exemplo6: ponteiros de hardware já preenchidos na imagem do executável (dados iniciais, como em .data),
# e uma global que o código sobrescreve com valor desconhecido. Sem código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	send
	addiu	$a0, $zero, 2
	jal	clobber
	addiu	$a0, $zero, 5
	jal	use_bad
	nop
1:	j	1b
	nop

send:
	lui	$t2, %hi(ptr_idx)
	lw	$t3, %lo(ptr_idx)($t2)
	nop
	sb	$zero, 0($t3)
	lui	$t2, %hi(ptr_cmd)
	lw	$t4, %lo(ptr_cmd)($t2)
	nop
	sb	$a0, 0($t4)
	jr	$ra
	nop

clobber:
	lui	$t2, %hi(ptr_bad)
	jr	$ra
	sw	$a0, %lo(ptr_bad)($t2)

use_bad:
	lui	$t2, %hi(ptr_bad)
	lw	$t3, %lo(ptr_bad)($t2)
	nop
	sb	$zero, 0($t3)
	jr	$ra
	nop

ptr_idx:
	.word	0x1f801800
ptr_cmd:
	.word	0x1f801801
ptr_bad:
	.word	0x1f801810
