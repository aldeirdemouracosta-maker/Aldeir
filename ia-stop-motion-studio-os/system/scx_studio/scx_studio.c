/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Loader for scx_studio: loads and attaches the scheduler, pins its maps
 * under /sys/fs/bpf/scx_studio (ia-sms-modo writes the mode and the studio's
 * processes there) and runs until SIGINT/SIGTERM or until the kernel ejects
 * the scheduler.
 *
 *   scx_studio [-m captura|edicao|ia|render|normal]
 */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <scx/common.h>
#include "scx_studio.h"
#include "scx_studio.bpf.skel.h"

#define PIN_DIR "/sys/fs/bpf/scx_studio"

static volatile int exit_req;

static void sigint_handler(int sig)
{
	exit_req = 1;
}

static int mode_from_name(const char *name)
{
	static const char *names[] = { "normal", "captura", "edicao", "ia", "render" };

	for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); i++)
		if (!strcmp(name, names[i]))
			return i;
	return -1;
}

int main(int argc, char **argv)
{
	struct scx_studio *skel;
	struct bpf_link *link;
	struct studio_cfg cfg = { .mode = STUDIO_NORMAL };
	__u32 zero = 0;
	int opt;

	while ((opt = getopt(argc, argv, "m:h")) != -1) {
		switch (opt) {
		case 'm': {
			int m = mode_from_name(optarg);
			if (m < 0) {
				fprintf(stderr, "modo desconhecido: %s\n", optarg);
				return 1;
			}
			cfg.mode = m;
			break;
		}
		default:
			fprintf(stderr, "uso: %s [-m captura|edicao|ia|render|normal]\n", argv[0]);
			return opt != 'h';
		}
	}

	signal(SIGINT, sigint_handler);
	signal(SIGTERM, sigint_handler);

	skel = SCX_OPS_OPEN(studio_ops, scx_studio);
	SCX_OPS_LOAD(skel, studio_ops, scx_studio, uei);

	if (bpf_map_update_elem(bpf_map__fd(skel->maps.studio_cfg), &zero, &cfg, BPF_ANY))
		fprintf(stderr, "aviso: não foi possível definir o modo inicial\n");

	mkdir(PIN_DIR, 0755);
	unlink(PIN_DIR "/cfg");
	unlink(PIN_DIR "/tasks");
	if (bpf_map__pin(skel->maps.studio_cfg, PIN_DIR "/cfg") ||
	    bpf_map__pin(skel->maps.studio_tasks, PIN_DIR "/tasks"))
		fprintf(stderr, "aviso: mapas não fixados em %s (bpffs montado?)\n", PIN_DIR);

	link = SCX_OPS_ATTACH(skel, studio_ops, scx_studio);
	printf("scx_studio ativo (modo %u)\n", cfg.mode);
	fflush(stdout);

	while (!exit_req && !UEI_EXITED(skel, uei))
		sleep(1);

	bpf_link__destroy(link);
	unlink(PIN_DIR "/cfg");
	unlink(PIN_DIR "/tasks");
	rmdir(PIN_DIR);
	UEI_REPORT(skel, uei);
	scx_studio__destroy(skel);
	return 0;
}
