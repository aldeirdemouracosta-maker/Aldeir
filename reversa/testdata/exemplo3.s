# exemplo3: stubs de BIOS, função recursiva e referência a string. Não contém código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	jal	bios_malloc
	addiu	$a0, $zero, 0x100
	lui	$a0, %hi(msg)
	jal	puts_like
	addiu	$a0, $a0, %lo(msg)
	jal	countdown
	addiu	$a0, $zero, 5
	jal	bios_b_stub
	nop
1:	j	1b
	nop

bios_malloc:
	addiu	$t2, $zero, 0xa0
	jr	$t2
	addiu	$t1, $zero, 0x33

bios_b_stub:
	addiu	$t2, $zero, 0xb0
	jr	$t2
	addiu	$t1, $zero, 0x07

puts_like:
	lbu	$t0, 0($a0)
	nop
	beq	$t0, $zero, 2f
	nop
	jal	bios_b_stub
	addiu	$a0, $a0, 1
2:	jr	$ra
	nop

countdown:
	beq	$a0, $zero, 3f
	nop
	addiu	$sp, $sp, -8
	sw	$ra, 0($sp)
	jal	countdown
	addiu	$a0, $a0, -1
	lw	$ra, 0($sp)
	addiu	$sp, $sp, 8
3:	jr	$ra
	nop

msg:
	.asciz	"Ola, mundo PS1 teste"
	.align	2
