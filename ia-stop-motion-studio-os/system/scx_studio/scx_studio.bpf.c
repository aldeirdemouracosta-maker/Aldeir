/* SPDX-License-Identifier: GPL-2.0 */
/*
 * scx_studio — sched_ext scheduler of IA Stop-Motion Studio OS.
 *
 * A weighted vtime scheduler (like scx_simple) with one global queue, plus
 * two task classes registered by user space through the pinned map
 * "studio_tasks" (tgid → class):
 *
 *   UI      the studio app: in Captura/Edição it gets short slices and a
 *           vtime head start, so the live view and the timeline never stutter
 *   WORKER  its heavy children (ffmpeg, melt, sd-cli, whisper-cli, …): in
 *           IA/Render they get long slices (fewer context switches, better
 *           cache use); in Captura/Edição they yield to the UI
 *
 * The current mode lives in the pinned array "studio_cfg" and is switched at
 * run time by ia-sms-modo. Anything unknown is scheduled fairly, and if the
 * scheduler misbehaves the kernel falls back to the default scheduler.
 */
#include <scx/common.bpf.h>
#include "scx_studio.h"

char _license[] SEC("license") = "GPL";

#define SHARED_DSQ	0
#define SLICE_UI	(3ULL * 1000 * 1000)	/* 3 ms */
#define SLICE_WORKER	(20ULL * 1000 * 1000)	/* 20 ms */

UEI_DEFINE(uei);

static u64 vtime_now;

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, u32);
	__type(value, struct studio_cfg);
} studio_cfg SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_HASH);
	__uint(max_entries, 4096);
	__type(key, u32);	/* tgid */
	__type(value, u32);	/* enum studio_class */
} studio_tasks SEC(".maps");

static u32 current_mode(void)
{
	u32 zero = 0;
	struct studio_cfg *cfg = bpf_map_lookup_elem(&studio_cfg, &zero);

	return cfg ? cfg->mode : STUDIO_NORMAL;
}

static u32 task_class(const struct task_struct *p)
{
	u32 tgid = p->tgid;
	u32 *cls = bpf_map_lookup_elem(&studio_tasks, &tgid);

	return cls ? *cls : CLASS_OTHER;
}

static bool interactive_mode(u32 mode)
{
	return mode == STUDIO_CAPTURA || mode == STUDIO_EDICAO;
}

static bool throughput_mode(u32 mode)
{
	return mode == STUDIO_IA || mode == STUDIO_RENDER;
}

/* Time slice for a task in the current mode. */
static u64 task_slice(u32 cls, u32 mode)
{
	if (cls == CLASS_UI && interactive_mode(mode))
		return SLICE_UI;
	if (cls == CLASS_WORKER && throughput_mode(mode))
		return SLICE_WORKER;
	return SCX_SLICE_DFL;
}

s32 BPF_STRUCT_OPS(studio_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
	bool is_idle = false;
	s32 cpu;

	cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
	if (is_idle)
		scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, task_slice(task_class(p), current_mode()), 0);
	return cpu;
}

void BPF_STRUCT_OPS(studio_enqueue, struct task_struct *p, u64 enq_flags)
{
	u32 mode = current_mode(), cls = task_class(p);
	u64 vtime = p->scx.dsq_vtime;

	/* Sleepers can bank at most one slice of credit. */
	if (time_before(vtime, vtime_now - SCX_SLICE_DFL))
		vtime = vtime_now - SCX_SLICE_DFL;

	if (interactive_mode(mode)) {
		if (cls == CLASS_UI)
			vtime -= 2 * SCX_SLICE_DFL;	/* run ahead of everyone */
		else if (cls == CLASS_WORKER)
			vtime += SCX_SLICE_DFL;		/* background work waits */
	}

	scx_bpf_dsq_insert_vtime(p, SHARED_DSQ, task_slice(cls, mode), vtime, enq_flags);
}

void BPF_STRUCT_OPS(studio_dispatch, s32 cpu, struct task_struct *prev)
{
	scx_bpf_dsq_move_to_local(SHARED_DSQ, 0);
}

void BPF_STRUCT_OPS(studio_running, struct task_struct *p)
{
	if (time_before(vtime_now, p->scx.dsq_vtime))
		vtime_now = p->scx.dsq_vtime;
}

void BPF_STRUCT_OPS(studio_stopping, struct task_struct *p, bool runnable)
{
	u64 slice = task_slice(task_class(p), current_mode());
	/* The mode may have changed while the task ran: never underflow. */
	u64 used = slice > p->scx.slice ? slice - p->scx.slice : 0;

	/* Charge the time used, scaled by the inverse of the task's weight. */
	p->scx.dsq_vtime += used * 100 / p->scx.weight;
}

void BPF_STRUCT_OPS(studio_enable, struct task_struct *p)
{
	p->scx.dsq_vtime = vtime_now;
}

s32 BPF_STRUCT_OPS_SLEEPABLE(studio_init)
{
	return scx_bpf_create_dsq(SHARED_DSQ, -1);
}

void BPF_STRUCT_OPS(studio_exit, struct scx_exit_info *ei)
{
	UEI_RECORD(uei, ei);
}

SCX_OPS_DEFINE(studio_ops,
	       .select_cpu	= (void *)studio_select_cpu,
	       .enqueue		= (void *)studio_enqueue,
	       .dispatch	= (void *)studio_dispatch,
	       .running		= (void *)studio_running,
	       .stopping	= (void *)studio_stopping,
	       .enable		= (void *)studio_enable,
	       .init		= (void *)studio_init,
	       .exit		= (void *)studio_exit,
	       .name		= "studio");
