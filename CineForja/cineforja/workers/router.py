"""Roteamento de tarefas pesadas para a GPU adequada."""

CUDA_TASKS = {"llm", "video", "heavy_image", "consistency"}
VULKAN_TASKS = {"light_image", "audio", "upscale"}


def choose_worker(task_type: str) -> str:
    if task_type in CUDA_TASKS:
        return "cuda"  # Tesla P100
    if task_type in VULKAN_TASKS:
        return "vulkan"  # RX 570
    return "cpu"
