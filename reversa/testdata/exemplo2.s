# exemplo2: programa de teste do reversa (MIPS-I, PS1). Laços, chamadas encadeadas, DMA, timers,
# CD-ROM, espera de VBlank e um salto indireto por tabela. Não contém código de jogo.
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	lui	$sp, 0x8020
	addiu	$sp, $sp, -32
	jal	gpu_reset
	nop
	jal	wait_vblank
	nop
	lui	$a0, 0x8001
	ori	$a0, $a0, 0x0300
	jal	checksum
	addiu	$a1, $zero, 64
	addu	$s0, $v0, $zero
	lui	$a0, 0x8001
	jal	dma_to_gpu
	addiu	$a1, $zero, 16
	jal	dispatch
	addiu	$a0, $zero, 1
main_loop:
	jal	wait_vblank
	nop
	jal	read_timer
	nop
	j	main_loop
	nop

gpu_reset:
	lui	$t0, 0x1f80
	sw	$zero, 0x1814($t0)
	lui	$t1, 0x0300
	ori	$t1, $t1, 0x0001
	sw	$t1, 0x1814($t0)
	jr	$ra
	nop

wait_vblank:
	lui	$t0, 0x1f80
1:	lw	$t1, 0x1070($t0)
	nop
	andi	$t1, $t1, 1
	beq	$t1, $zero, 1b
	nop
	sw	$zero, 0x1070($t0)
	jr	$ra
	nop

checksum:
	addu	$v0, $zero, $zero
2:	beq	$a1, $zero, 3f
	nop
	lbu	$t0, 0($a0)
	addiu	$a0, $a0, 1
	addu	$v0, $v0, $t0
	beq	$zero, $zero, 2b
	addiu	$a1, $a1, -1
3:	jr	$ra
	nop

dma_to_gpu:
	lui	$t0, 0x1f80
	sw	$a0, 0x10a0($t0)
	sll	$t1, $a1, 16
	ori	$t1, $t1, 0x0010
	sw	$t1, 0x10a4($t0)
	lui	$t2, 0x0100
	ori	$t2, $t2, 0x0201
	sw	$t2, 0x10a8($t0)
	jr	$ra
	nop

read_timer:
	lui	$t0, 0x1f80
	lw	$v0, 0x1100($t0)
	jr	$ra
	nop

cd_command:
	lui	$t0, 0x1f80
	sb	$zero, 0x1800($t0)
	sb	$a0, 0x1801($t0)
	jr	$ra
	nop

dispatch:
	sll	$a0, $a0, 2
	lui	$t0, 0x8001
	ori	$t0, $t0, 0x0400
	addu	$t0, $t0, $a0
	lw	$t1, 0($t0)
	nop
	jr	$t1
	nop

handler_a:
	addiu	$sp, $sp, -8
	sw	$ra, 0($sp)
	jal	read_timer
	nop
	lw	$ra, 0($sp)
	addiu	$sp, $sp, 8
	jr	$ra
	nop

handler_b:
	addiu	$sp, $sp, -8
	sw	$ra, 0($sp)
	jal	cd_command
	addiu	$a0, $zero, 1
	lw	$ra, 0($sp)
	addiu	$sp, $sp, 8
	jr	$ra
	nop
