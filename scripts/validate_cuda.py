import json, sys, torch
r = dict(torch=torch.__version__, cuda=torch.version.cuda, available=torch.cuda.is_available(), built_arches=torch._C._cuda_getArchFlags())
if not r['available']:
    r['status']='BLOCKED_NO_CUDA_DEVICE_OR_DRIVER'
    print(json.dumps(r, indent=2)); sys.exit(2)
r.update(gpu=torch.cuda.get_device_name(0), compute=torch.cuda.get_device_capability(0), arches=torch.cuda.get_arch_list())
if r['compute'] != (6, 0) or 'P100' not in r['gpu'] or 'sm_60' not in r['arches']:
    r['status']='BLOCKED_WRONG_GPU_OR_BUILD'
    print(json.dumps(r, indent=2)); sys.exit(3)
a=torch.randn(1024,1024,device='cuda')
b=a@a
torch.cuda.synchronize()
assert torch.isfinite(b).all().item()
r.update(status='PASS', shape=list(b.shape), device=str(b.device), allocated=torch.cuda.memory_allocated(), reserved=torch.cuda.memory_reserved())
print(json.dumps(r, indent=2))
