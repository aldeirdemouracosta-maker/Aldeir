	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	lui	$t0, 0x1f80
	ori	$t0, $t0, 0x1810
	jal	init_gpu
	nop
	jal	send
	addiu	$a0, $zero, 7
	jal	send
	addiu	$a0, $zero, 9
loop:
	j	loop
	nop
init_gpu:
	lui	$t1, 0x1f80
	sw	$zero, 0x1814($t1)
	lui	$t2, 0x1f80
	lw	$v0, 0x1070($t2)
	jr	$ra
	nop
send:
	lui	$t1, 0x1f80
	sw	$a0, 0x1810($t1)
	lui	$t3, 0x8002
	lw	$t4, 0($t3)
	jalr	$t4
	nop
	jr	$ra
	nop
